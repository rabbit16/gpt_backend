# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:57 下午
# @Author  : rabbit
# @File    : models.py
# @Software: PyCharm

from sqlalchemy import String, Integer, Boolean, Column, DateTime, ForeignKey, func
from .database import Base
class User(Base):
    __tablename__ = "tb_note_user"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(40), index=True, unique=True)
    user_name = Column(String(30))
    role_num = Column(Integer)
    regular_user = Column(Integer)
    plus_user_count = Column(Integer)
    dept_code = Column(String(40))
    dept_name = Column(String(40))
    user_loc = Column(String(20))
    user_ip = Column(String(18))
    dev_passwd = Column(String(20))  # 这里的密码是明文存储，安全性不高
    valid_flag = Column(String(6))  # 这个是不是可以用bool类型
    create_time = Column(DateTime)
    update_time = Column(DateTime)
    plus_user_expire_time = Column(DateTime, default=func.now())
    regular_user_expire_time = Column(DateTime, default=func.now())
    update_manager = Column(String(30))  # 更新人 TODO
class UserAuthority(Base):
    __tablename__ = "tb_task_user_authority"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tb_task_base", ondelete="CASCADE"), unique=True)
    user_id = Column(String(40), unique=True)
    task_role = Column(String(40))
    create_time = Column(DateTime)
    update_time = Column(DateTime)