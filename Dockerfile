# syntax=docker/dockerfile:experimental
FROM python:3.6

EXPOSE 80
RUN apt-get update -y
RUN mkdir ~/.ssh && echo "Host git*\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config

ENV DJANGO_SETTINGS_MODULE=ifxbilling.settings

WORKDIR /app

COPY requirements.txt /app

ARG DJVOCAB_COMMIT=a0cfeba93ea805d3861e97e9c38fd27447e5b58a
ARG IFXURLS_COMMIT=549af42dbe83d07b12dd37055a5ec6368d4b649e
ARG NANITES_CLIENT_COMMIT=a11ff96ccb2c888d0d07ac97f27de1153463bf59
ARG IFXUSER_COMMIT=a7cf433a6572fa5a9fc969a6e6de7ff3e5297a0c
ARG IFXAUTH_COMMIT=afcaad2b05f5dd90e86e53b2de864bef04c91898
ARG FIINE_CLIENT_COMMIT=1701982585571f0a8af8698888bf46426ee21a4d

RUN --mount=type=ssh pip install --upgrade pip && \
    pip install 'Django>2.2,<3' && \
    pip install 'djangorestframework>3.9.1,<3.12.0' && \
    pip install git+ssh://git@github.com/harvardinformatics/djvocab.git@${DJVOCAB_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxurls.git@${IFXURLS_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/nanites.client.git@${NANITES_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxuser.git@${IFXUSER_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxauth.git@${IFXAUTH_COMMIT} && \
    pip install git+ssh://git@gitlab-int.rc.fas.harvard.edu/informatics/fiine.client.git@${FIINE_CLIENT_COMMIT} && \
    pip install -r requirements.txt

CMD ./wait-for-it.sh -t 60 db:3306 && \
    ./manage.py makemigrations && \
    ./manage.py migrate && \
    ./manage.py runserver 0.0.0.0:80 --insecure

