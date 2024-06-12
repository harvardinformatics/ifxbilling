# syntax=docker/dockerfile:experimental
FROM python:3.10-bullseye

EXPOSE 80
RUN apt-get update -y
RUN mkdir ~/.ssh && echo "Host git*\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config

ENV DJANGO_SETTINGS_MODULE=ifxbilling.settings

WORKDIR /app

COPY requirements.txt /app

ARG DJVOCAB_COMMIT=bf8c985168a5a5b402758b97475b3e4e7b7fb49c
ARG IFXURLS_COMMIT=30d093a410e405dac650e7904e6e140e87a9e95b
ARG NANITES_CLIENT_COMMIT=bf5ac0ba32790463a663025cdea2dee6ea9342e9
ARG IFXUSER_COMMIT=cd6a1836a81cb94667b539d30e6c18e254047bda
ARG IFXAUTH_COMMIT=1e4fa823367f5309cf8e49857bbcf1f5931aa9d8
ARG IFXMAIL_CLIENT_COMMIT=5f4adf6e5de1f7db716c1cde5b63dda6ec8c241c
ARG FIINE_CLIENT_COMMIT=e6e60518a41e9fb4231ceaf42fc2ca5bf86f674a
ARG IFXVALIDCODE_COMMIT=4dd332c5a8e13d904a90da014094406a81b617e6

RUN --mount=type=ssh pip install --upgrade pip && \
    pip install 'Django>4,<5' && \
    pip install 'djangorestframework==3.14.0' && \
    pip install git+ssh://git@github.com/harvardinformatics/djvocab.git@${DJVOCAB_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxurls.git@${IFXURLS_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/nanites.client.git@${NANITES_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxauth.git@${IFXAUTH_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxmail.client.git@${IFXMAIL_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxuser.git@${IFXUSER_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/fiine.client.git@${FIINE_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxec.git@${IFXVALIDCODE_COMMIT} && \
    pip install -r requirements.txt

CMD ./wait-for-it.sh -t 120 db:3306 && \
    ./manage.py makemigrations && \
    ./manage.py migrate && \
    ./manage.py applyDevBillingData && \
    ./manage.py runserver 0.0.0.0:80 --insecure

