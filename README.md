# Bambou

A web app managing students, teachers, tutors and marks.

## Install

Clone the repository:

  `git clone https://github.com/CourtBouillon/bambou.git /path/to/bambou`

Create a virtual environment:

  `python3 -m venv /path/to/venv`

Install dependencies:

  `/path/to/venv/bin/pip install flask`

Configure Bambou (`/path/to/bambou.cfg`):

```py
DB = '/path/to/bambou.db'
SMTP_HOSTNAME = 'smtp.example.com'
SMTP_LOGIN = 'login'
SMTP_PASSWORD = 'password'
SMTP_FROM = 'sender@example.com'
```

Configure uWSGI:

```ini
[uwsgi]
chdir = /path/to/bambou
socket = /tmp/bambou.socket
plugin = python3

processes = 4
threads = 1

module = bambou:app

virtualenv = /path/to/venv

env = BAMBOU_CONFIG=/path/to/bambou.cfg
```

Configure Nginx:

```
server {
   listen 443 ssl http2;
   listen [::]:443;
   server_name bambou.example.com;

   ssl on;
   ssl_certificate /path/to/fullchain.pem;
   ssl_certificate_key /path/to/privkey.pem;

   location /static {
      root /path/to/bambou/bambou;
   }

   location / {
      include uwsgi_params;
      uwsgi_pass unix:/tmp/bambou.socket;
   }
}
```
