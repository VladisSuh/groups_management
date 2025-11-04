--Реализация базовых механизмов без персистентности
CREATE TABLE IF NOT EXISTS person_group (
    id SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS person (
    id SERIAL PRIMARY KEY,
    group_id INT REFERENCES person_group(id),

    last_name  VARCHAR(100) NOT NULL CHECK (
        last_name ~ '^[А-ЯЁ][а-яё-]{1,}$'
    ),

    first_name VARCHAR(100) NOT NULL CHECK (
        first_name ~ '^[А-ЯЁ][а-яё-]{1,}$'
    ),

    middle_name VARCHAR(100) CHECK (
        middle_name IS NULL OR middle_name ~ '^[А-ЯЁ][а-яё-]{1,}$'
    ),

    birth_date DATE NOT NULL,

    gender CHAR(1) NOT NULL CHECK (gender IN ('М','Ж')),

    address TEXT NOT NULL CHECK (length(trim(address)) > 0),

    phone VARCHAR(20) CHECK (
        phone ~ '^\+7\(\d{3}\)\d{3}-\d{2}-\d{2}$'
    ),

    email VARCHAR(255) CHECK (
        email ~ '^[A-Za-z0-9]+([._][A-Za-z0-9]+)*@[A-Za-z0-9]+([.-][A-Za-z0-9]+)*$'
    )
);

--Реализация с персистентностью

--Что-то вроде таблицы коммитов
CREATE TABLE IF NOT EXISTS change_set (
  id BIGSERIAL PRIMARY KEY,
  authored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  author TEXT,
  reason TEXT
);


-- текущее состояние, по одной строке на группу
ALTER TABLE person
  ADD COLUMN IF NOT EXISTS change_id BIGINT REFERENCES change_set(id),
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT true;

-- история предыдущих версий
CREATE TABLE IF NOT EXISTS person_history (
  id BIGSERIAL PRIMARY KEY,
  group_id INT NOT NULL REFERENCES person_group(id),
  change_id BIGINT REFERENCES change_set(id),

  last_name  VARCHAR(100) NOT NULL,
  first_name VARCHAR(100) NOT NULL,
  middle_name VARCHAR(100),
  birth_date DATE NOT NULL,
  gender CHAR(1) NOT NULL CHECK (gender IN ('М','Ж')),
  address TEXT NOT NULL,
  phone VARCHAR(20),
  email VARCHAR(255),

  valid_from TIMESTAMPTZ NOT NULL,
  valid_to   TIMESTAMPTZ NOT NULL
);

-- Вьюха
CREATE OR REPLACE VIEW person_current AS
SELECT *
FROM person
WHERE is_current = true;


-- текущее состояние и связь с группой
CREATE INDEX IF NOT EXISTS i_person_current ON person(is_current) WHERE is_current;
CREATE INDEX IF NOT EXISTS i_person_group   ON person(group_id);

-- для поиска (по установленным правилам)
CREATE INDEX IF NOT EXISTS i_person_match
  ON person (gender, first_name, COALESCE(middle_name,''), last_name)
  WHERE is_current;

-- быстрый поиск по контактам (точное совпадение)
CREATE INDEX IF NOT EXISTS i_person_phone  ON person(phone)  WHERE is_current;
CREATE INDEX IF NOT EXISTS i_person_email  ON person(email)  WHERE is_current;

-- для истории (диапазоны)
CREATE INDEX IF NOT EXISTS i_hist_group_from_to ON person_history (group_id, valid_from, valid_to);

--Реализация витрины
CREATE OR REPLACE VIEW person_vitrine AS
SELECT
  p.group_id,
  p.last_name, p.first_name, p.middle_name,
  p.birth_date, p.gender,
  p.address, p.phone, p.email,
  p.created_at, p.change_id
FROM person p
WHERE p.is_current = true;

-- дедупликация
DROP TRIGGER IF EXISTS trg_assign_person_group ON person;
DROP FUNCTION IF EXISTS assign_person_group();
DROP FUNCTION IF EXISTS find_matching_group(varchar, varchar, varchar, char, text, varchar, varchar);

-- персистентность
DROP TRIGGER IF EXISTS trg_version_person_after_insert ON person;
DROP FUNCTION IF EXISTS version_person_after_insert();

-- запрет прямых обновлений (мешает бэкенду)
DROP TRIGGER IF EXISTS t_no_update_person ON person;
DROP FUNCTION IF EXISTS forbid_direct_write();