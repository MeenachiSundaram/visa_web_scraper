# -*- coding: utf8 -*-
# from pyvirtualdisplay import Display
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

import time
import random
import json
from datetime import datetime

from telegram import send_message, send_photo
from pagem import send_page
from creds import (
    username,
    password,
    url_id,
    schedule_date,
    facility_id,
    country_code,
    validation_text,
    notification_chat_id,
)

USERNAME = username
PASSWORD = password
SCHEDULE_ID = url_id
MY_SCHEDULE_DATE = schedule_date
COUNTRY_CODE = country_code
FACILITY_ID = facility_id

REGEX_CONTINUE = "//a[contains(text(),'Continue')]"


# def MY_CONDITION(month, day): return int(month) == 11 and int(day) >= 5
def MY_CONDITION(month, day):
    return True  # No custom condition wanted for the new scheduled date


STEP_TIME = 0.5  # time between steps (interactions with forms): 0.5 seconds
RETRY_TIME = 60 * 10  # wait time between retries/checks for available dates: 10 minutes
EXCEPTION_TIME = 60 * 30  # wait time when an exception occurs: 30 minutes
COOLDOWN_TIME = 60 * 60  # wait time when temporary banned (empty list): 60 minutes

DATE_URL = f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment"
EXIT = False

# Setting Chrome options to run the scraper headless.
chrome_options = Options()
# chrome_options.add_argument("--disable-extensions")
# chrome_options.add_argument("--disable-gpu")
# chrome_options.add_argument("--no-sandbox") # linux only
# chrome_options.add_argument("--headless") # Comment for visualy debugging
# chrome_options.add_argument('window-size=1920,1080')
# chrome_options.add_argument("--start-maximized")

# Initialize the chromediver (must be installed and in PATH)
# Needed to implement the headless option
driver = webdriver.Chrome(options=chrome_options)


def do_login_action():
    print("\tinput email")
    user = driver.find_element(By.ID, "user_email")
    user.send_keys(USERNAME)
    time.sleep(random.randint(1, 3))

    print("\tinput pwd")
    pw = driver.find_element(By.ID, "user_password")
    pw.send_keys(PASSWORD)
    time.sleep(random.randint(1, 3))

    print("\tclick privacy")
    box = driver.find_element(By.CLASS_NAME, "icheckbox")
    box.click()
    time.sleep(random.randint(1, 3))

    print("\tcommit")
    btn = driver.find_element(By.NAME, "commit")
    btn.click()
    time.sleep(random.randint(1, 3))

    try:
        Wait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, REGEX_CONTINUE))
        )
        print("\tlogin successful!")
    except TimeoutError:
        print("\tLogin failed!")
        login()


def has_website_changed():
    driver.get(APPOINTMENT_URL)
    time.sleep(random.randint(5, 10))
    # Checks for changes in the site. Returns True if a change was found.
    print("\tChecking for changes in UI.")
    # # For debugging false positives.
    with open("debugging/page_source.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    # Getting main text
    main_page = driver.find_element(By.ID, "main")
    print(main_page.text)
    # For debugging false positives.
    with open("debugging/main_page", "w") as f:
        f.write(main_page.text)
    # If the "no appointment" text is not found return True. A change was found.
    return validation_text not in main_page.text


def login():
    # Bypass reCAPTCHA
    driver.get(f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv")
    time.sleep(STEP_TIME)
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    print("Login start...")
    href = driver.find_element(
        By.XPATH, '//*[@id="header"]/nav/div[2]/div[1]/ul/li[3]/a'
    )
    href.click()
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))

    print("\tclick bounce")
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    do_login_action()


def get_date():
    driver.get(DATE_URL)
    if not is_logged_in():
        login()
        return get_date()
    else:
        content = driver.find_element(By.TAG_NAME, "pre").text
        date = json.loads(content)
        return date


def get_time(date):
    time_url = TIME_URL % date
    driver.get(time_url)
    content = driver.find_element(By.TAG_NAME, "pre").text
    data = json.loads(content)
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time


def reschedule(date):
    global EXIT
    print(f"Starting Reschedule ({date})")

    time = get_time(date)
    driver.get(APPOINTMENT_URL)

    data = {
        "utf8": driver.find_element_by_name("utf8").get_attribute("value"),
        "authenticity_token": driver.find_element_by_name(
            "authenticity_token"
        ).get_attribute("value"),
        "confirmed_limit_message": driver.find_element_by_name(
            "confirmed_limit_message"
        ).get_attribute("value"),
        "use_consulate_appointment_capacity": driver.find_element_by_name(
            "use_consulate_appointment_capacity"
        ).get_attribute("value"),
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,  # 108
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": time,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.125 Safari/537.36",
        "Referer": APPOINTMENT_URL,
        "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"],
    }

    r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
    if r.text.find("Successfully Scheduled") != -1:
        msg = f"Rescheduled Successfully! {date} {time}"
        send_message(msg)
        send_photo(driver.get_screenshot_as_png())
        EXIT = True
    else:
        msg = f"Reschedule Failed. {date} {time}"
        send_message(msg)
        send_photo(driver.get_screenshot_as_png())


def is_logged_in():
    content = driver.page_source
    if content.find("error") != -1:
        return False
    return True


def print_dates(dates):
    print("Available dates:")
    for d in dates:
        print("%s \t business_day: %s" % (d.get("date"), d.get("business_day")))
    print()


last_seen = None


def get_available_date(dates):
    global last_seen

    def is_earlier(date):
        my_date = datetime.strptime(MY_SCHEDULE_DATE, "%Y-%m-%d")
        new_date = datetime.strptime(date, "%Y-%m-%d")
        result = my_date > new_date
        print(f"Is {my_date} > {new_date}:\t{result}")
        return result

    print("Checking for an earlier date:")
    for d in dates:
        date = d.get("date")
        if is_earlier(date) and date != last_seen:
            _, month, day = date.split("-")
            if MY_CONDITION(month, day):
                last_seen = date
                return date


def push_notification(dates):
    msg = "date: "
    for d in dates:
        msg = msg + d.get("date") + "; "
    send_message(msg)
    send_photo(driver.get_screenshot_as_png())


if __name__ == "__main__":
    login()
    retry_count = 0
    while 1:
        if retry_count > 6000:
            break
        try:
            print("------------------")
            print(datetime.today())
            print(f"Retry count: {retry_count}")
            print()

            if has_website_changed():
                print('A change was found. Notifying it.')
                send_message('A change was found. Here is an screenshot.')
                send_photo(driver.get_screenshot_as_png())
                send_page('A change was found. paging it.')

            dates = get_date()[:5]
            # if not dates:
            #     msg = "List is empty"
            #     send_message(msg, notification_chat_id)
            #     EXIT = True
            print_dates(dates)
            date = get_available_date(dates)
            print()
            print(f"New date: {date}")
            if date:
                reschedule(date)
                push_notification(dates)

            if EXIT:
                print("------------------exit")
                break

            if not dates:
                msg = "Dates List is empty, Retry in {RETRY_TIME} seconds"
                send_message(msg, notification_chat_id)
                # EXIT = True
                time.sleep(RETRY_TIME)

        except:
            retry_count += 1
            time.sleep(EXCEPTION_TIME)

    if not EXIT:
        send_message("HELP! Crashed.")
        send_photo(driver.get_screenshot_as_png())
