@echo off

echo.
echo.
echo.
echo.

echo ���ڱ���py�ļ�
echo.
echo.

..\..\..\runtime\python\python.exe pyc_modifier.py --path=. --compile=Y

echo.
echo.
echo �Ѿ�������ϣ��Ժ���Զ��رմ��ڡ�
echo.
echo.

ping 127.0.0.1 > NUL
ping 127.0.0.1 > NUL
