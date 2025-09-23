import os

import requests
from flask.cli import load_dotenv


class Bark(object):
    def __init__(self):
        self.token = os.environ.get('BARK_TOKEN')

    def notify(self, title, content, icon=None, image=None, url=None):
        if self.token:
            if not icon:
                icon = 'https://yd.jiadan.li/static/img/logo.jpg'

            if not url:
                url = 'https://yd.jiadan.li'

            params = {
                'title': title,
                'body': content,
                'icon': icon,
                'url': url,
            }
            if image:
                params['image'] = image

            resp = requests.post(f'https://bark.aproxy.cn/{self.token}/', json=params)
            print(resp.text)


if __name__ == '__main__':
    bark = Bark()
    bark.notify('Test Title', 'This is a test notification from Bark.')
    print("Notification sent successfully.")
