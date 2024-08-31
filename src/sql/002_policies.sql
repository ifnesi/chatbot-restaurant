CREATE TABLE IF NOT EXISTS public.policies (
    id VARCHAR PRIMARY KEY,
    description VARCHAR
);
INSERT INTO public.policies (id, description) VALUES
    ('food-discount', 'Food orders including at least one starter, one main, and one dessert receive a 10% discount (it excludes beverages)'),
    ('drinks-discount', 'Beverages are not discounted, no exceptions'),
    ('service-tax', 'A 12.5% service tax applies to all bills, separate from optional gratuities'),
    ('currency', 'Transactions in GBP only'),
    ('allergens', 'All potential allergens in offerings are transparently listed. Services tailored for dietary needs to ensure customer safety and satisfaction'),
    ('alcohol', 'Responsible service, customers must be at least 21 years old for alcohol to ensure a safe, enjoyable dining experience');
