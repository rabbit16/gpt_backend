如果在安装 MySQL 时已经设置了 root 用户的密码，您可以尝试以下方法来查看初始设置的密码：

1. 打开命令行界面或终端窗口。
2. 输入以下命令以进入 MySQL 的交互式命令行界面：
   ```
   mysql -u root -p
   ```
   这里的 `-p` 参数表示需要输入密码。
3. 输入您初始设置的 root 密码，并按下回车键。
4. 如果密码正确，您将会成功登录到 MySQL。此时您可以看到 `mysql>` 提示符。
5. 如果密码错误，控制台将显示一个错误消息。如果密码被遗忘或无法确定，您可能需要重置 root 密码。

如果初始设置的密码并不起作用，您可以尝试重置 root 密码的操作。具体步骤如下：

1. 停止 MySQL 服务。您可以在命令行界面中运行以下命令：
   ```
   sudo service mysql stop
   ```
2. 使用以下命令以跳过授权表启动 MySQL 服务：
   ```
   sudo mysqld_safe --skip-grant-tables &
   ```
3. 打开另一个命令行界面或终端窗口，并输入以下命令以进入 MySQL 的交互式命令行界面：
   ```
   mysql -u root
   ```
4. 进入 MySQL 后，使用以下命令来更改 root 密码：
   ```
   FLUSH PRIVILEGES;
   ALTER USER 'root'@'localhost' IDENTIFIED BY 'new_password';
   ```
   将 `'new_password'` 替换为您想要设置的新密码。
5. 退出 MySQL 命令行界面：
   ```
   exit;
   ```
6. 在第一个命令行界面上，停止 MySQL 服务并重新启动：
   ```
   sudo service mysql stop
   sudo service mysql start
   ```