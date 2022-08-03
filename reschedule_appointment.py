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
import logging
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
# EXCEPTION_TIME = 60 * 30  # wait time when an exception occurs: 30 minutes
# COOLDOWN_TIME = 60 * 60  # wait time when temporary banned (empty list): 60 minutes

DATE_URL = f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment"
# EXIT = False

logging.basicConfig(level=logging.INFO, filename="visa.log", filemode="a+", format="%(asctime)-15s %(levelname)-8s %(message)s")


# To run Chrome in a virtual display with xvfb (just in Linux)
# display = Display(visible=0, size=(800, 600))
# display.start()

# Setting Chrome options to run the scraper headless.
chrome_options = Options()
# chrome_options.add_argument("--disable-extensions")
# chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox") # linux only
chrome_options.add_argument("--headless") # Comment for visualy debugging
chrome_options.add_argument('window-size=1920,1080')
# chrome_options.add_argument("--start-maximized")

# Initialize the chromediver (must be installed and in PATH)
# Needed to implement the headless option
driver = webdriver.Chrome(options=chrome_options)

def do_login_action():
    logging.info("\tinput email")
    user = driver.find_element(By.ID, "user_email")
    user.send_keys(USERNAME)
    time.sleep(random.randint(1, 3))

    logging.info("\tinput pwd")
    pw = driver.find_element(By.ID, "user_password")
    pw.send_keys(PASSWORD)
    time.sleep(random.randint(1, 3))

    logging.info("\tclick privacy")
    box = driver.find_element(By.CLASS_NAME, "icheckbox")
    box.click()
    time.sleep(random.randint(1, 3))

    logging.info("\tcommit")
    btn = driver.find_element(By.NAME, "commit")
    btn.click()
    time.sleep(random.randint(1, 3))

    try:
        Wait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, REGEX_CONTINUE))
        )
        logging.info("\tlogin successful!")
    except TimeoutError:
        logging.warning("\tLogin failed!")
        login()


def login():
    # Bypass reCAPTCHA
    driver.get(f"https://ais.usvisa-info.com/en-{COUNTRY_CODE}/niv")
    time.sleep(STEP_TIME)
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    logging.info("Login start...")
    href = driver.find_element(
        By.XPATH, '//*[@id="header"]/nav/div[2]/div[1]/ul/li[3]/a'
    )
    href.click()
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))

    logging.info("\tclick bounce")
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
    logging.info(f"Got time successfully! {date} {time}")
    return time


def reschedule(date):
    global EXIT
    logging.info(f"Starting Reschedule ({date})")

    time = get_time(date)
    driver.get(APPOINTMENT_URL)

    data = {
        "utf8": driver.find_element(by=By.NAME, value='utf8').get_attribute('value'),
        "authenticity_token": driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value'),
        "confirmed_limit_message": driver.find_element(by=By.NAME, value='confirmed_limit_message').get_attribute('value'),
        "use_consulate_appointment_capacity": driver.find_element(by=By.NAME, value='use_consulate_appointment_capacity').get_attribute('value'),
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": time,
    }

    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
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
    logging.info("Available dates:")
    for d in dates:
        logging.info("%s \t business_day: %s" % (d.get("date"), d.get("business_day")))


last_seen = None


def get_available_date(dates):
    global last_seen

    def is_earlier(date):
        my_date = datetime.strptime(MY_SCHEDULE_DATE, "%Y-%m-%d")
        new_date = datetime.strptime(date, "%Y-%m-%d")
        result = my_date > new_date
        logging.info(f"Is {my_date} > {new_date}:\t{result}")
        return result

    logging.info("Checking for an earlier date:")
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


def run_visa_scraper(appointment_url, validation_text):
    def has_website_changed():
        '''Checks for changes in the site. Returns True if a change was found.'''
        # Getting the website to check
        driver.get(appointment_url)
        time.sleep(random.randint(5, 10))

        logging.info('\t\tChecking for changes in UI.')
        
        # # For debugging false positives.
        with open('debugging/page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)

        # Getting main text
        main_page = driver.find_element(By.ID, 'main')

        # For debugging false positives.
        with open('debugging/main_page', 'w') as f:
            f.write(main_page.text)

        # If the "no appointment" text is not found return True. A change was found. 
        if validation_text not in main_page.text:
            logging.info(f"\t\t'{validation_text}' - text NOT FOUND in UI")
            return True
        else:
            logging.info(f"\t\t'{validation_text}' - text found in UI")
            return False


    login()
    time.sleep(random.randint(1, 3))
    while True:
        current_time = time.strftime('%a, %d %b %Y %H:%M:%S', time.localtime())
        logging.info(f'Starting a new check at {current_time}.')
        if has_website_changed():
            logging.info('A change was found. Notifying it.')
            send_photo(driver.get_screenshot_as_png())
            send_message('A change was found. Here is an screenshot.')
            send_page('A change was found. paging it.')
            
            x = get_date()
            dates = x[:5]
            logging.info(f"List of dates: {dates}")
            if dates:
                print_dates(dates)
                date = get_available_date(dates)
                logging.info(f"New date: {date}")
                if date:
                    reschedule(date)
                    push_notification(dates)

                # Closing the driver before quiting the script.
                driver.close()
                exit()
        else:
            x = get_date()
            dates = x[:5]
            logging.info(f"List of dates: {dates}")
            if dates:
                print_dates(dates)
                date = get_available_date(dates)
                logging.info(f"New date: {date}")
                if date:
                    reschedule(date)
                    push_notification(dates)

                # Closing the driver before quiting the script.
                driver.close()
                exit()
                
            logging.info(f'No change was found. Checking again in {RETRY_TIME} seconds.')
            send_message(f'No change was found. Checking again in {RETRY_TIME} seconds.', notification_chat_id, True)
            send_photo(driver.get_screenshot_as_png(), notification_chat_id, True)
            logging.info('- '*30)
            time.sleep(RETRY_TIME)



if __name__ == "__main__":
    try:
        run_visa_scraper(APPOINTMENT_URL,validation_text)
    except Exception as err:
        logging.warning(err)
        send_message("HELP! Crashed.")
        send_message(err)
