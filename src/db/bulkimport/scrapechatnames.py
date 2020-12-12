import requests
from bs4 import BeautifulSoup

# From the web:
#wikiusers = "https://indieweb.org/chat-names"
#page = requests.get(wikiusers)
#soup = BeautifulSoup(page.content, 'lxml')

# From a file:
wikiusers = "indieweb.org_chat-names.html"
with open(wikiusers, 'r') as fr:
    page = fr.read()
soup = BeautifulSoup(page, 'lxml')

# <a href="http://michael-lewis.com" class="external u-url" style="background-image:none;padding-right:0">

with open('chatnames.txt', 'w') as fo:
    for link in soup.find_all('a', class_="external u-url"):
        print(link['href'])
        fo.write(str(link['href']) + "\n")
