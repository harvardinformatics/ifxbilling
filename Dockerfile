# syntax=docker/dockerfile:experimental
FROM python:3.6

EXPOSE 80
RUN apt-get update -y
RUN mkdir ~/.ssh && echo "Host git*\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config

ENV DJANGO_SETTINGS_MODULE=ifxbilling.settings

WORKDIR /app

COPY requirements.txt /app

ARG DJVOCAB_COMMIT=a0cfeba93ea805d3861e97e9c38fd27447e5b58a
ARG IFXURLS_COMMIT=30d093a410e405dac650e7904e6e140e87a9e95b
ARG NANITES_CLIENT_COMMIT=a11ff96ccb2c888d0d07ac97f27de1153463bf59
ARG IFXUSER_COMMIT=760d637acbecec9e246c9a717e73d635ec2d7b2e
ARG IFXAUTH_COMMIT=afcaad2b05f5dd90e86e53b2de864bef04c91898
ARG IFXMAIL_CLIENT_COMMIT=5fc6d834c76c0f66d823ff0b5d384ab7b30009b0
ARG FIINE_CLIENT_COMMIT=d0c0658fedde41bd97755bfef47ecd835ac7ef9b
ARG IFXVALIDCODE_COMMIT=4dd332c5a8e13d904a90da014094406a81b617e6

RUN --mount=type=ssh pip install --upgrade pip && \
    pip install 'Django>2.2,<3' && \
    pip install 'djangorestframework>3.9.1,<3.12.0' && \
    pip install git+ssh://git@github.com/harvardinformatics/djvocab.git@${DJVOCAB_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxurls.git@${IFXURLS_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/nanites.client.git@${NANITES_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxauth.git@${IFXAUTH_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxmail.client.git@${IFXMAIL_CLIENT_COMMIT} && \
    pip install git+ssh://git@github.com/harvardinformatics/ifxuser.git@${IFXUSER_COMMIT} && \
    pip install git+ssh://git@gitlab-int.rc.fas.harvard.edu/informatics/fiine.client.git@${FIINE_CLIENT_COMMIT} && \
    pip install git+ssh://git@gitlab-int.rc.fas.harvard.edu/informatics/ifxvalidcode.git@${IFXVALIDCODE_COMMIT} && \
    pip install -r requirements.txt

CMD ./wait-for-it.sh -t 120 db:3306 && \
    ./manage.py makemigrations && \
    ./manage.py migrate && \
    ./manage.py applyDevBillingData && \
    ./manage.py runserver 0.0.0.0:80 --insecure

