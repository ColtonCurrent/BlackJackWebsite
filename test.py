#!/usr/bin/env python3
import selenium
from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Firefox()
driver.get('http://localhost:8080/login')
sleep(1)

driver.find_element(By.XPATH, "//input[@name='username']").send_keys('logan')
driver.find_element(By.XPATH, "//input[@name='password']").send_keys('logan')
sleep(1)
driver.find_element(By.XPATH, "//input[@type='submit']").click()





