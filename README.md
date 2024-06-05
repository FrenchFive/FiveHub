# FiveHub
HOUDINI CUSTOM DATABASE OF ASSET 

## SUMMARY :
- [FEATURES](#features-)
  <sub>What FiveHub is able to do</sub>
- [SETUP](#setup-)
  <sub>How to install FiveHub</sub>
- [UPCOMING](#upcoming-)
  <sub>What is in work</sub>

## FEATURES :
### 1. SAVE TO HUB
  - **SELECT AND CLICK**
    - AUTOMATIC PYTHON FORMATING
    - RENAMING GEO TO ASSET NAME
  - **IMAGE CAPTURE**
    - VIEWPORT RESETTING
      - SELECT CURRENT VIEWPORT
      - RESETTING FRAME
      - FRAMING SELECTED OBJECT
    - VIEWPORT CAPTURE
  - **DATABASE ENTRY**
  - **AUTOMATIC FILE REPATHING**
    - MOVING FILE TO THE ASSET FOLDER
    - REPATHING THE PYTHON FILES PATH
    
### 2. LOAD FROM HUB
  - SQL REQUEST TO THE DB
  - QT INTERFACE
    - BUTTON PER DB ENTRY
    - GRID LAYOUT BASED ON WINDOW SCALE
    - CUSTOM WRAP LAYOUT
  - PYTHON EXECUTION
  - CATEGORIES SEPARATION

------

## SETUP :

### 1. CHOOSE YOUR DIRECTORY :

DIRECTORY IS IMPORTANT

This directory will hold :
  - Code
  - Toolbar
  - Assets
  - Database

### 2. OPEN CMD FROM DIRECTORY :

You can achieve this either by traveling through your **File Explorer** 
```
%windir%\explorer.exe
```

Right Clicking the folder :: **"Open in Terminal"**

OR 

Opening your CMD : 
```
cd C:/Users/.../your-path
```

### 3. GIT CLONE :

Cloning the project in your CMD :
```
git clone https://github.com/FrenchFive/FiveHub.git
```

### 5. CHOOSE HOUDINI VERSION :

TO MATCH YOUR HOUDINI VERSION IT IS IMPORTANT TO NOTE THE HOUDINI VERSION IN THE ``` setup.py ```

DEFAULT :: ""19.5""

![CODE](https://github.com/FrenchFive/FiveHub/assets/105274118/f73e1004-619b-4816-9431-808ddd26943a)


![HOUDINI_VERSION](https://github.com/FrenchFive/FiveHub/assets/105274118/be1633d4-633c-49ea-8c53-09f8d04d8875)


### 6. RUN SETUP.PY

Answer to setup Questions :

> Do you want to change the version ? (y/n)

<sub>This will allow FiveHub to determine where is located your Houdini Env Folder.</sub>
- yes :
  - Input a custom version : 20.0 ( no needs of the last dot 19.5 ~~.605~~ )
- no :
  - Use the default version `19.5`


> Do you want to install locally ? (y/n)

<sub>This will allow FiveHub to add lines to your .env File, This process will add the Toolbar folder and the Python Script in the list of folders Houdini needs to check during the launch</sub>
- yes :
  - Will add the necessary lines to your local `.env` file.
- no :
  - Will **NOT** add the necessary lines to your local `.env` file.

> [!WARNING]
> Not allowing FiveHub to change Env Variable may lead to FiveHub to not be found or recognized by Houdini. 

Recommened answer are : **`no`** / **`yes`**

### 7. LAUNCH HOUDINI 

------
## UPCOMING : 
- [x] REPATHING AND MOVING EXTERNAL FILES
- [ ] MAKING SURE THAT FILES DONT OVERWRITE EACH OTHER
- [ ] FUZZY FIND ??
- [x] CATEGORIES
- [x] Filename more readable
