# syntax=docker/dockerfile:experimental
FROM python:3.6

EXPOSE 80
RUN apt-get update -y
RUN mkdir ~/.ssh && echo "Host github.com\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config

ENV DJANGO_SETTINGS_MODULE=ifxbilling.settings

WORKDIR /app

COPY requirements.txt /app

ARG DJVOCAB_COMMIT=a0cfeba93ea805d3861e97e9c38fd27447e5b58a
ARG IFXURLS_COMMIT=72f75b3fcc9446fc5095ad747b3ed53d05bc4799
ARG IFXUSER_COMMIT=056d06c5592ca72c911fffdc9c7436441f78ce31
ARG IFXAUTH_COMMIT=afcaad2b05f5dd90e86e53b2de864bef04c91898

RUN --mount=type=ssh pip install --upgrade pip && \
    pip install 'Django>2.2,<3' && \
    pip install 'djangorestframework>3.9.1,<3.12.0' && \
    pip install git+ssh://git@github.com/harvardinformatics/djvocab.git@${DJVOCAB_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxurls.git@${IFXURLS_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxuser.git@${IFXUSER_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxauth.git@${IFXAUTH_COMMIT} && \
    pip install -r requirements.txt

CMD ./wait-for-it.sh -t 60 db:3306 && \
    ./manage.py makemigrations && \
    ./manage.py migrate && \
    ./manage.py runserver 0.0.0.0:80 --insecure

