from typing import Union, List
from pydantic import BaseModel, Field
from utils.public_schemas import ResponseOwn


class UserResponse(BaseModel):
    name: str
    email: Union[str, None] = None
    code: Union[str, None] = None
    is_delete: Union[bool, None] = None


class UserRequestFormat(BaseModel):
    name: str = Field(None, description="该参数为用户姓名")
    password: str = Field(..., description="该参数为用户密码，前端需要md5后传入后端，必填参数")
    email: Union[str, None] = Field(None, description="该参数为用户的email")
    code: Union[str, None] = Field(None, description="用户的网名")
    telephone: Union[str, None] = Field(None, description="用户电话")
    username: Union[str, None] = Field(None, description="匿名注册时由系统生成的用户名")
    anonymous: bool = Field(False, description="匿名注册，不填手机号和邮箱")
    is_anonymous: Union[bool, None] = Field(False, description="是否匿名用户")
    username_login: Union[bool, None] = Field(False, description="是否允许用户名登录")
    is_staff: Union[bool] = Field(False, description="是否为超级管理员")
    is_delete: Union[bool, None] = Field(False, description="软删除，默认为False")


class UserLoginFormat(BaseModel):
    password: Union[str, None] = None
    userId: Union[str, None] = Field(None, description="这个是用户的电话号码或者邮箱")


class PasswordCodeFormat(BaseModel):
    email: str = Field(..., description="接收验证码的邮箱")


class PasswordResetFormat(BaseModel):
    email: str
    code: str
    password: str = Field(..., description="新密码，前端 md5 后传入")


class ProfileUpdateFormat(BaseModel):
    name: str = Field(..., description="名称")
    telephone: Union[str, None] = None
    email: Union[str, None] = None
    old_password: Union[str, None] = None
    new_password: Union[str, None] = None


class GptAskFormat(BaseModel):
    contextId: Union[str, None] = Field(None, description="13位的时间戳，用来标识一个对话")
    withoutContext: Union[bool, None] = Field(False, description="控制是否需要上下文关联，默认不开启")
    prompt: str = Field(..., description="这个就是用户的问句")
    userId: int = Field(..., description="用户的Id")
    mode: str = Field(None, description="模型参数")


class CreateNewChatContext(BaseModel):
    userId: int = Field(..., description="这个是用户的Id，用来创建相关的对话")


class QueryUserContextList(BaseModel):
    userId: int = Field(..., description="用户的Id")
    chat_id: Union[str, None] = Field(None, description="如果传了就返回单一对话，没传就返回用户对话的所有集合")
    page: int = Field(1, description="页数")
    page_num: int = Field(5, description="一页展示多少个数据")
    allContext: bool = Field(True, description="是否获取所有的上下文列表")


class SearchChatContext(BaseModel):
    userId: int
    keyword: str = Field(..., min_length=1, max_length=200)
    page: int = Field(1, ge=1)
    page_num: int = Field(10, ge=1, le=50)


class SaveChatContextFormat(BaseModel):
    userId: int = Field(..., description="用户的Id")
    contextId: str = Field(..., description="会话 id，对应 createChat 返回的 newChatId")
    prompt: str = Field(..., description="用户问题")
    gpt: str = Field(..., description="模型回复")
    mode: Union[str, None] = Field(None, description="模型名，仅作记录")
    start_time: Union[str, None] = Field(None, description="提问时间")
    answer_time: Union[str, None] = Field(None, description="回答时间")


class UserPayApi(BaseModel):
    userId: int = Field(..., description="用户的Id")
    money: float = Field(..., description="支付的金额")
    function_code: str = Field(..., description="功能名称")


class BillFormat(BaseModel):
    bill_id: str = Field(..., description="订单id，13位时间戳")
    money: float = Field(..., description="所付金额")
    function_id: int = Field(..., description="功能点id")
    is_delete: int = Field(False, description="软删除")
    generate_by: int = Field(..., description="用户id")


class BillQueryFormat(BaseModel):
    userId: int = Field(..., description="用户的id")
    page: int = Field(1, description="页数")
    page_num: int = Field(5, description="一页展示多少个数据")


class UserInfoQuery(BaseModel):
    userId: int = Field(..., description="用户的id")


class VerifyPayAgainFormat(BaseModel):
    codeNum: str = Field(..., description="这个是订单的唯一标识，需要传入")


class UserExist(BaseModel):
    userId: int = Field(..., description="用户的id")
    completion: float = Field(None, description="对话消耗的token数量")
    prompt: float = Field(None, description="prompt消耗的数量")
