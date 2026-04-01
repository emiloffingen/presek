
from categories import detect_category, detect_topic
from entities import extract_entities

test_cases = [
    {
        "title": "Шкендија и Вардар ремизираа во дербито на Првата фудбалска лига",
        "desc": "Натпреварот заврши без голови, а двајцата тренери беа задоволни од играта на своите фудбалери."
    },
    {
        "title": "Мицкоски на средба со амбасадорот на Германија во Скопје",
        "desc": "Претседателот на Владата разговараше за европските интеграции и економската соработка со Берлин."
    },
    {
        "title": "Епл го претстави новиот iPhone со вградена вештачка интелигенција",
        "desc": "Новиот процесор овозможува побрзо извршување на задачите и подобра работа со апликациите."
    }
]

print("--- ТЕСТ НА БЕСПЛАТНИТЕ ЛОКАЛНИ ПРАВИЛА ---\n")

for i, tc in enumerate(test_cases, 1):
    title = tc["title"]
    desc = tc["desc"]
    
    # 1. Geographic Category
    cat = detect_category(title, description=desc)
    
    # 2. Thematic Topic
    topic = detect_topic(title, description=desc)
    
    # 3. Entities
    ents = extract_entities(title + " " + desc)
    ent_names = [e["name"] for e in ents]
    
    print(f"Вест {i}: {title}")
    print(f"  -> Категорија: {cat}")
    print(f"  -> Тема: {topic}")
    print(f"  -> Субјекти (Entities): {', '.join(ent_names) if ent_names else 'Нема'}")
    print("-" * 40)

print("\nСите овие резултати се добиени ЛОКАЛНО без ниту еден AI повик.")
