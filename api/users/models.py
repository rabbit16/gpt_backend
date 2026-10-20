# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:59 下午
# @Author  : rabbit
# @File    : models.py
# @Software: PyCharm
import datetime
import json
import time

from sqlalchemy import String, Integer, Boolean, Column, DateTime, ForeignKey, Float, JSON, TEXT, Index, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship
from settings.database import Base


# from settings.models import User
# 用户表单
class User(Base):
    __tablename__ = "tb_user"
    user_id = Column(Integer, primary_key=True, index=True, unique=True, autoincrement="auto")  # 用户id，作为主键
    name = Column(String(100))  # 姓名
    code = Column(String(100), index=True)  # 网络代号
    telephone = Column(String(11), index=True, unique=True)  # 手机电话
    email = Column(String(100), index=True, unique=True)
    password = Column(String(100), index=True)
    is_staff = Column(Boolean, default=False)  # 是否为超级管理员
    last_login_time = Column(DateTime, default=func.now())
    is_activate = Column(Boolean, default=True)  # 是否活跃
    register_time = Column(DateTime, default=func.now())  # 注册时间
    update_time = Column(DateTime, default=func.now())  # 更新时间
    plus_user_expire_time = Column(DateTime, default=func.now())  # 超级会员过期时间
    plus_use_buy = Column(Integer, default=0)  # gpt4模型使用
    draw_count = Column(Integer, default=0)  # gpt4模型使用
    regular_user_expire_time = Column(DateTime, default=func.now())  # 普通会员过期时间
    token = Column(Float)  # 每天的使用次数
    plus_user_count = Column(Integer, default=6)  # gpt4模型使用
    is_new = Column(Integer, default=1)  # 标识是否为新用户
    is_year = Column(Integer, default=1)  # 标识是否为年度用户，如果为2就是gpt4 plus会员
    is_quarter = Column(Integer, default=1)  # 标识是否为季度用户，1为季度， 2为1天体验, 3为gpt4plus会员 4为gpt普通会员
    regular_user = Column(Integer)  # 普通会员用户

    is_delete = Column(Boolean, default=False)  # 软删除字段
    token_daily = Column(Float, default=0)  # 每天的token
    input_token = Column(Float, default=0)  # 总输入token
    output_token = Column(Float, default=0)  # 总输出token
    discount = Column(Float, default=1)  # 折扣
    ask_num = Column(Integer, default=0)  # 折扣
    answer_num = Column(Integer, default=0)  # 折扣
    money_rate = Column(Float, default=1)  # 倍率调整
    phone_key_revoked = Column(Boolean, nullable=False, default=False, server_default="0")  # 生成过 sk- 后，手机号不能再当密钥
    username = Column(String(64), unique=True, index=True, nullable=True)  # 登录用户名，全局唯一
    username_login = Column(Boolean, nullable=False, default=False, server_default="0")  # 打开后才允许用用户名登录
    is_anonymous = Column(Boolean, nullable=False, default=False, server_default="0")  # 匿名注册，无手机号和邮箱

    def to_dict(self):
        now_time = datetime.datetime.fromtimestamp(time.time())
        # if self.is_year == 1 or self.is_quarter == 2:
        #     self.plus_user_count = "无限"
        #     self.token = "无限"
        # elif self.plus_user_expire_time > now_time and self.is_year == 1 and self.is_quarter != 0:
        #     self.token = "无限"
        # else:
        #     self.token = self.token + self.regular_user

        return {
            "user_id": self.user_id,
            "userName": self.name,
            "userCode": self.code,
            "token": self.token,
            "is_staff": self.is_staff,
            "plus_user_expire_time": self.plus_user_expire_time,
            "regular_user_expire_time": self.regular_user_expire_time,
            "plus_user_count": "无折扣" if self.discount == 1 else self.discount
        }


class UserApiKey(Base):
    """用户自行创建的 API 密钥。只有 is_active 且未删除用户的 key 能调用中转。"""
    __tablename__ = "tb_user_api_key"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True, nullable=False)
    api_key = Column(String(80), unique=True, index=True, nullable=False)
    name = Column(String(40), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


# 标签表单
class Tag(Base):
    __tablename__ = "tb_tag"
    tag_id = Column(Integer, primary_key=True, index=True, autoincrement="auto")
    tag_name = Column(String(50))  # 标签名称
    level = Column(Integer)  # 标签等级 一级 二级 等等
    insert_time = Column(DateTime, default=func.now())  # 插入时间
    is_delete = Column(Boolean, default=False)  # 软删除


# 提示词分类表单
class TagPrompt(Base):
    __tablename__ = "tb_prompt_tag"
    tag_id = Column(Integer, ForeignKey("tb_tag.tag_id", ondelete="CASCADE"), index=True, primary_key=True)  # 用户id
    prompt_id = Column(Integer, ForeignKey("tb_prompt.prompt_id", ondelete="CASCADE"),
                       index=True, primary_key=True)  # 联合的功能点id
    insert_time = Column(DateTime, default=func.now())  # 插入时间
    update_time = Column(DateTime, default=func.now())  # 更新时间
    is_delete = Column(Boolean, default=False)  # 软删除


# # 对话表单，利用时间戳为单位
# class Chat(Base):
#     __tablename__ = "tb_chat"  # 数据库中表的名字
#     chat_id = Column(Integer, index=True, primary_key=True, autoincrement=True)
#     user_id = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True)
#     chat_list = Column(JSON, default="")
#     update_time = Column(DateTime, default=func.now())  # 注册时间
#     is_delete = Column(Boolean, default=False)  # 软删除  # 一对一关系限定

# 功能记录表
class FunctionCode(Base):
    __tablename__ = "tb_function"
    function_id = Column(Integer, primary_key=True, index=True, autoincrement="auto")
    function_code = Column(String(50), index=True, unique=True)
    insert_time = Column(DateTime, default=func.now())  # 插入时间
    update_time = Column(DateTime, default=func.now())  # 更新时间
    function_name = Column(String(50), index=True, unique=True)  # 功能中文名


# 用户行为记录表
class UserActionRecord(Base):
    __tablename__ = "tb_user_action_record"
    user_id = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True, primary_key=True)  # 用户id
    function_id = Column(Integer, ForeignKey("tb_function.function_id", ondelete="CASCADE"),
                         index=True, primary_key=True)  # 联合的功能点id
    use_num = Column(Integer, default=0)  # 使用次数
    update_time = Column(DateTime, default=func.now())  # 更新时间


# prompt表单
class Prompt(Base):
    __tablename__ = "tb_prompt"
    prompt_id = Column(Integer, primary_key=True, index=True, autoincrement="auto")
    prompt_text = Column(TEXT)
    insert_time = Column(DateTime, default=func.now())
    insert_by = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True)
    update_time = Column(DateTime, default=func.now())
    update_by = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True)
    is_delete = Column(Boolean, default=False)  # 软删除
    index_prompt_text = Index('p_text', 'prompt_text', mysql_length=255)


# prompt使用表
class PromptUse(Base):
    __tablename__ = "tb_prompt_use"
    prompt_id = Column(Integer, ForeignKey("tb_prompt.prompt_id", ondelete="CASCADE"), index=True, primary_key=True)
    used_by = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True, primary_key=True)
    insert_time = Column(DateTime)
    update_time = Column(DateTime)
    is_delete = Column(Boolean, default=False)
    use_num = Column(Integer)


class UserContext(Base):
    __tablename__ = "tb_user_context"
    context_id = Column(String(13), index=True, primary_key=True, default=str(int(time.time() * 1000)))
    context_uuid = Column(String(100), index=True, default=None)
    used_by = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True)
    insert_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now())
    is_delete = Column(Boolean, default=False)
    context = Column(JSON, default=json.dumps([]))  # 该字段记录用户对话
    current_id_gpt = Column(String(100), index=True, default=None)
    auth = Column(String(100), index=True, default=None)
    parent_id = Column(String(5000), index=True, default=None)


# 账单表
class Bill(Base):
    __tablename__ = "tb_bill"
    bill_id = Column(String(50), primary_key=True, index=True, autoincrement="auto")
    generate_time = Column(DateTime, default=func.now())
    generate_by = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True)
    money = Column(Float)
    function_id = Column(Integer, ForeignKey("tb_function.function_id", ondelete="CASCADE"),
                         index=True)  # 联合的功能点id
    is_delete = Column(Boolean, default=False)
    delete_time = Column(DateTime, default=None)


# 保密人员名单
class TeacherSecret(Base):
    __tablename__ = "tb_teacher_secret"
    id = Column(Integer, primary_key=True, autoincrement="auto", index=True)
    user_id = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"),
                     index=True)  # 联合的功能点id


class UserFeedback(Base):
    __tablename__ = "tb_user_feedback"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    content = Column(TEXT, nullable=False)
    contact = Column(String(100), default="")
    nickname = Column(String(50), default="")
    anonymous = Column(Boolean, default=True)
    user_id = Column(Integer, index=True, nullable=True)
    ip = Column(String(64), default="")
    user_agent = Column(String(255), default="")
    insert_time = Column(DateTime, default=func.now())
    is_read = Column(Boolean, default=False)
    is_delete = Column(Boolean, default=False)
    reply = Column(TEXT, default="")
    reply_time = Column(DateTime, default=None)


class Announcement(Base):
    """站点公告：后台可增删改，前台展示历史，登录后弹最新一条。"""
    __tablename__ = "tb_announcement"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    title = Column(String(200), nullable=False, default="")
    content = Column(TEXT, nullable=False)
    status = Column(Integer, default=1, index=True)  # 1 上线 / 0 下线
    sort = Column(Integer, default=0)  # 越大越靠前；同级按 id 倒序
    insert_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())
    is_delete = Column(Boolean, default=False)


class SoftwareCategory(Base):
    """软件下载分类。"""
    __tablename__ = "tb_software_category"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(50), nullable=False, default="")
    status = Column(Integer, default=1, index=True)  # 1 上线 / 0 下线
    sort = Column(Integer, default=0)
    insert_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())
    is_delete = Column(Boolean, default=False)


class Software(Base):
    """软件下载条目。下载地址是网盘等第三方链接，站点不托管文件。"""
    __tablename__ = "tb_software"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    category_id = Column(Integer, index=True, nullable=False)
    name = Column(String(200), nullable=False, default="")
    summary = Column(TEXT, nullable=False, default="")
    cover_url = Column(MEDIUMTEXT, default="")
    version = Column(String(50), default="")
    links = Column(JSON, default=list)  # [{label, url, code}]
    status = Column(Integer, default=1, index=True)
    sort = Column(Integer, default=0)
    insert_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())
    is_delete = Column(Boolean, default=False)


class UserTask(Base):
    """用户自己的任务。状态默认由最新日志判断，也可以手动改。"""
    __tablename__ = "tb_user_task"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(Integer, ForeignKey("tb_user.user_id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(80), nullable=False, default="")
    detail = Column(String(500), nullable=False, default="")
    log_text = Column(MEDIUMTEXT, nullable=False, default="")
    status = Column(String(16), nullable=False, default="pending", index=True)
    status_source = Column(String(16), nullable=False, default="log")  # log | manual
    suggested_status = Column(String(16), nullable=False, default="pending")
    decision = Column(String(300), nullable=False, default="")
    insert_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())
    is_delete = Column(Boolean, default=False)
    __table_args__ = (
        Index("ix_user_task_owner_status", "user_id", "is_delete", "status"),
    )
