# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:58 下午
# @Author  : rabbit
# @File    : settings.py
# @Software: PyCharm
import json
import time
from kafka import KafkaProducer, TopicPartition, KafkaAdminClient, KafkaConsumer
import logging
from kafka.admin import NewTopic
SHOW_NUM_EVERY_PAGE = 5