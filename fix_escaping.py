with open("web/src/components/SearchIsland.tsx", "r") as f:
    content = f.read()

content = content.replace("\\'", "'")

with open("web/src/components/SearchIsland.tsx", "w") as f:
    f.write(content)
