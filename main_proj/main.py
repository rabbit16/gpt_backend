# -*- coding: utf-8 -*-
# @Time    : 2022/9/20 2:08 下午
# @Author  : rabbit
# @File    : main.py
# @Software: PyCharm
# from fastapi import FastAPI
#
# app = FastAPI()
#
# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
from fastapi import FastAPI, File, UploadFile

app = FastAPI()


@app.post("/files/")
async def create_file(file: bytes = File()):
    return {"file_size": len(file)}


@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile):
    # print(file.content_type)
    return {"filename": file.filename}









# if __name__ == '__main__':
#     app.run

