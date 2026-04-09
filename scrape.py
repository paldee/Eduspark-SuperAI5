import requests
import re
from bs4 import BeautifulSoup
import pandas as pd

#package สำหรับจัดการ html เรียกว่า BeautifulSoup
def get_soup(url):
    with requests.get(url) as r:
        soup = BeautifulSoup(r.text, features='html.parser')
    return soup

#ดึงข้อมูล html จากเว็บไซต์มาเปลี่ยนเป็น soup
url = f'https://findstudentship.eef.or.th/scholarship?grade=%E0%B8%97%E0%B8%B8%E0%B8%81%E0%B8%A3%E0%B8%B0%E0%B8%94%E0%B8%B1%E0%B8%9A&cost=%E0%B8%97%E0%B8%B8%E0%B8%99%E0%B8%97%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%AB%E0%B8%A1%E0%B8%94&genre=%E0%B8%97%E0%B8%B8%E0%B8%99%E0%B9%83%E0%B8%AB%E0%B9%89%E0%B9%80%E0%B8%9B%E0%B8%A5%E0%B9%88%E0%B8%B2'
soup = get_soup(url)

# print(soup)

target = soup.find("div", class_= re.compile("mb-5$"))
target2 = soup.select("mb-5")

print(target)
print(target2)