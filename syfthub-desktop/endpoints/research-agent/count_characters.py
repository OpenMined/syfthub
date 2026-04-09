import os

# Get a list of files in the current directory
files = os.listdir()

total_characters = 0

# Iterate over each file
for file in files:
    # Check if the item is a file (not a directory)
    if os.path.isfile(file):
        # Open the file and read its contents
        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            total_characters += len(content)

print(f'Total characters in all files: {total_characters}')
