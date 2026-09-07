import requests
from bs4 import BeautifulSoup

HEADERS = {
    # A normal browser UA avoids some basic bot-blocking.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# url='https://www.geeksforgeeks.org/python/python-programming-language-tutorial/'
url="https://candidates.sos.mn.gov/CandidateFilingResults.aspx?county=0&municipality=0&schooldistrict=0&hospitaldistrict=0&level=1&party=0&federal=True&judicial=True&executive=True&senate=True&representative=True&title=&office=0&candidateid=0"

# Fetch and parse the page
res = requests.get(url, headers=HEADERS, timeout=30)
res.raise_for_status()
# print(res.status_code)
# print(res.content)
# exit(0)
soup = BeautifulSoup(res.content, 'html.parser')

# Find the main content container
# content = soup.find('div', class_='article--viewer_content')
# content = soup.find('div')
# content = soup.find_all('table')
content = soup.find_all('tr')
print(content)
# print(content.find_all('td'))
exit(0)

if content:
    # for para in content.find_all('p'):
    for para in content.find_all('td'):
        print(para.text.strip())
else:
    print("No article content found.")

