# FiveHub
HOUDINI CUSTOM DATABASE OF ASSET 

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

![image](https://github.com/FrenchFive/FiveHub/assets/105274118/f73e1004-619b-4816-9431-808ddd26943a)



### 6. RUN SETUP.PY


### 7. LAUNCH HOUDINI 

------
## UPCOMING : 
- [x] REPATHING AND MOVING EXTERNAL FILES
- [ ] MAKING SURE THAT FILES DONT OVERWRITE EACH OTHER 
- [ ] FUZZY FIND ??
- [ ] CATEGORIES
- [x] Filename more readable
- [x] CLOSING WINDOW HANDLING
