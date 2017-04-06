@echo off

set find=C:\Windows\system32\find
REG QUERY "HKLM\Hardware\Description\System\CentralProcessor\0" | %find% /i "x86" > NUL && set OS=32BIT || set OS=64BIT
if %OS%==32BIT set Software=Software
if %OS%==64BIT set Software=Software\Wow6432Node
for /f "usebackq tokens=4" %%a in (`REG QUERY "HKLM\%Software%\Python\PythonCore\2.7\InstallPath" /ve`) do (
    set python=%%a
)

if not exist venv (
    %python%\Scripts\virtualenv.exe venv
    call venv\Scripts\activate.bat
    pip install -U pip
)

call venv\Scripts\activate.bat
pip install -r requirements.txt
python setup.py
deactivate
