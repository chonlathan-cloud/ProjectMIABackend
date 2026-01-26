CREATE TABLE IF NOT EXISTS shop_publications (
  shop_id VARCHAR PRIMARY KEY REFERENCES shops(shop_id),
  is_published BOOLEAN NOT NULL DEFAULT FALSE,
  published_at TIMESTAMP NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
