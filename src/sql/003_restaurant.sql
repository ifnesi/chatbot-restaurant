CREATE TABLE IF NOT EXISTS public.restaurant (
    id VARCHAR PRIMARY KEY,
    description VARCHAR
);
INSERT INTO public.restaurant (id, description) VALUES
    ('name', 'StreamBite'),
    ('our-atmosphere', 'A happy, vibrant environment blending elegance with technology for a sensory dining experience. Bright, airy, and accented with digital art, it is an escape from the ordinary'),
    ('excellence-in-customer-service', 'Exceptional service is key to memorable dining. Our staff, ambassadors of unparalleled hospitality, ensure a personalized visit with attention to detail, anticipating needs for an exceptional experience'),
    ('culinary-philosophy', 'Focused on innovation and quality, emphasizing farm-to-table freshness. Each dish represents a creative exploration of flavors, prepared with precision and creativity. Our approach ensures a dining experience that celebrates culinary artistry'),
    ('community-and-sustainability', 'Committed to sustainability and community engagement, sourcing locally and minimizing environmental impact. Supporting us means choosing a business that cares for the planet and community well-being'),
    ('your-next-visit', 'Your destination for unforgettable dining, from three-course meals to casual experiences. Welcome to a journey where every bite tells a story, and every meal is an adventure');
