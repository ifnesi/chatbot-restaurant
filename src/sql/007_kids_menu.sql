CREATE TABLE IF NOT EXISTS public.kids_menu (
    id VARCHAR PRIMARY KEY,
    section VARCHAR,
    name VARCHAR,
    description VARCHAR,
    calories VARCHAR,
    fat VARCHAR,
    carbohydrates VARCHAR,
    protein VARCHAR,
    allergens VARCHAR,
    price REAL
);
INSERT INTO public.kids_menu (id, section, name, description, calories, fat, carbohydrates, protein, allergens, price) VALUES
    ('mini-cheese-quesadillas', 'starters', 'Mini Cheese Quesadillas', 'Cheesy and delicious mini quesadillas, served with a side of salsa', '150 kcal', '9g', '12g', '7g', 'Dairy,Gluten', 4),
    ('chicken-nuggets', 'starters', 'Chicken Nuggets', 'Crispy chicken nuggets served with ketchup and honey mustard dipping sauces', '200 kcal', '12g', '13g', '10g', 'Gluten', 4.5),
    ('mac-n-cheese', 'mains', 'Mac & Cheese', 'Creamy macaroni and cheese,a classic favorite', '300 kcal', '18g', '25g', '10g', 'Dairy,Gluten', 5),
    ('mini-burgers', 'mains', 'Mini Burgers', 'Three mini burgers on soft buns, served with fries', '400 kcal', '20g', '35g', '20g', 'Gluten', 6),
    ('fruit-punch', 'drinks', 'Fruit Punch', 'Sweet and refreshing fruit punch made with real fruit juice', '80 kcal', '0g', '20g', '0g', null, 2),
    ('milk', 'drinks', 'Milk', 'Cold,fresh milk. Choose from whole, 2%, or skim', '100 kcal (for whole milk)', '5g (for whole milk)', '12g', '8g', 'Dairy', 1.5),
    ('ice-cream-sundae', 'desserts', 'Ice Cream Sundae', 'Vanilla ice cream topped with chocolate syrup, whipped cream, and a cherry', '250 kcal', '15g', '25g', '5g', 'Dairy', 3),
    ('fruit-cup', 'desserts', 'Fruit Cup', 'A mix of fresh seasonal fruits', '90 kcal', '0g', '22g', '1g', null, 2.5);
