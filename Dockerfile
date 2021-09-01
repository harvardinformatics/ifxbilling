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
ARG IFXUSER_COMMIT=1306c46160e9f614e380401d7b067ae8cafb145d
ARG IFXAUTH_COMMIT=afcaad2b05f5dd90e86e53b2de864bef04c91898
ARG FIINE_CLIENT_COMMIT=60af4daed93303fa0bca118c57cf064f5b4f9157
ARG IFXVALIDCODE_COMMIT=4dd332c5a8e13d904a90da014094406a81b617e6

RUN --mount=type=ssh pip install --upgrade pip && \
    pip install 'Django>2.2,<3' && \
    pip install 'djangorestframework>3.9.1,<3.12.0' && \
    pip install git+ssh://git@github.com/harvardinformatics/djvocab.git@${DJVOCAB_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxurls.git@${IFXURLS_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/nanites.client.git@${NANITES_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxuser.git@${IFXUSER_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxauth.git@${IFXAUTH_COMMIT} && \
    pip install git+ssh://git@gitlab-int.rc.fas.harvard.edu/informatics/fiine.client.git@${FIINE_CLIENT_COMMIT} && \
    pip install git+ssh://git@gitlab-int.rc.fas.harvard.edu/informatics/ifxvalidcode.git@${IFXVALIDCODE_COMMIT} && \
    pip install -r requirements.txt

CMD ./wait-for-it.sh -t 60 db:3306 && \
    ./manage.py makemigrations && \
    ./manage.py migrate && \
    ./manage.py applyDevBillingData && \
    ./manage.py runserver 0.0.0.0:80 --insecure

