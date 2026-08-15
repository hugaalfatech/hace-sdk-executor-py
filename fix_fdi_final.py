# Fix script
fp = "src/executor_py/io/rac/cri/fdi.py"
with open(fp, "r", encoding="utf-8") as f:
    content = f.read()
print(len(content), "chars")
print("has marker:", "rac:import binding" in content)