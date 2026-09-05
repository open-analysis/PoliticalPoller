# File Policies and Expectations

## Descriptions
### File
Each file will have a description of the intention of said file. \
It may also include a high level description of intentions if necessary. \
#### Example
```python
"""
Description: This file contains the various file reader functions.
"""
```
### Function/Method
Each function/method will have a description of the intention of the function. \
It may also include a high level description of algorithm if necessary. \
The description will include the input/output parameters. \
The owner will be demarked with their name (or Github username). This may be skipped for methods. \
A backup or team may also be denoted if applicable. This may be skipped for methods. \
#### Example
```python
"""
Description: This function reads the input politician's file and returns a list of their information 
Param[in] input_file:       Input file path as a string to be read
Return List:                List of the politician's information
Owner: @opnanalysis
"""
def read_politician_file(input_file:str) -> List:
```
### Class
Each class will have a description of the intention of the class and the key variables/methods. \
The description will include the constructor and necessary input parameters for the class. \
The owner will be demarked with their name (or Github username). \
A backup or team may also be denoted if applicable. \
#### Example
```python
"""
Description: This class creates and stores information for a politician. 
Owner: @opnanalysis
"""
class politician():
```