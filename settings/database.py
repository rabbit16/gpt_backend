# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:56 下午
# @Author  : rabbit
# @File    : database.py
# @Software: PyCharm
from sqlalchemy import create_engine, event, select, exc
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import sessionmaker

from settings.env import get
from settings.macro import POOL_RECYCLE_TIME, MAX_POOL_SIZE, MAX_OVERFLOW, POOL_TIME_OUT

SQLALCHEMY_DATABASE_URL = get(
    "DATABASE_URL",
    "mysql+pymysql://root:root@localhost:3306/gpt_db",
)
def create_engine_inner():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_recycle=POOL_RECYCLE_TIME,
        pool_size=MAX_POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIME_OUT,
        # echo_pool=True,
        pool_pre_ping=True
    )

    @event.listens_for(engine, "engine_connect")
    def ping_connection(connection, branch):
        """
        连接控制，用来监控数据库连接的装饰器
        :param connection:
        :param branch:
        :return:
        """
        if branch:
            # this parameter is always False as of SQLAlchemy 2.0,
            # but is still accepted by the event hook.  In 1.x versions
            # of SQLAlchemy, "branched" connections should be skipped.
            return
        try:
            # run a SELECT 1.   use a core select() so that
            # the SELECT of a scalar value without a table is
            # appropriately formatted for the backend
            connection.scalar(select(1))
        except exc.DBAPIError as err:
            # catch SQLAlchemy's DBAPIError, which is a wrapper
            # for the DBAPI's exception.  It includes a .connection_invalidated
            # attribute which specifies if this connection is a "disconnect"
            # condition, which is based on inspection of the original exception
            # by the dialect in use.
            if err.connection_invalidated:
                # run the same SELECT again - the connection will re-validate
                # itself and establish a new connection.  The disconnect detection
                # here also causes the whole connection pool to be invalidated
                # so that all stale connections are discarded.
                connection.scalar(select(1))
            else:
                raise
    return engine


engine = create_engine_inner()
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)
Base = declarative_base()


