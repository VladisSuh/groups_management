--Реализация базовых механизмов без персистентности
CREATE TABLE person_group (
    id SERIAL PRIMARY KEY
);

CREATE TABLE person (
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

CREATE OR REPLACE FUNCTION find_matching_group(
    p_last_name  VARCHAR,
    p_first_name VARCHAR,
    p_middle_name VARCHAR,
    p_gender CHAR,
    p_address TEXT,
    p_phone VARCHAR,
    p_email VARCHAR
)
RETURNS INT AS $$
DECLARE
    v_group_id INT;
BEGIN
    SELECT p.group_id
    INTO v_group_id
    FROM person p
    WHERE
        p.gender = p_gender
        AND p.first_name = p_first_name
        AND (p.middle_name = p_middle_name OR (p.middle_name IS NULL AND p_middle_name IS NULL))
        AND (p_gender <> 'М' OR p.last_name = p_last_name)
        AND (
            (p.address = p_address)
            OR (p.phone IS NOT NULL AND p.phone = p_phone)
            OR (p.email IS NOT NULL AND p.email = p_email)
        )
    LIMIT 1;

    RETURN v_group_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION assign_person_group()
RETURNS TRIGGER AS $$
DECLARE
    v_group_id INT;
BEGIN
    v_group_id := find_matching_group(
        NEW.last_name,
        NEW.first_name,
        NEW.middle_name,
        NEW.gender,
        NEW.address,
        NEW.phone,
        NEW.email
    );

    IF v_group_id IS NOT NULL THEN
        NEW.group_id := v_group_id;
    ELSE
        INSERT INTO person_group DEFAULT VALUES RETURNING id INTO v_group_id;
        NEW.group_id := v_group_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- CREATE TRIGGER trg_assign_person_group
-- BEFORE INSERT ON person
-- FOR EACH ROW
-- EXECUTE FUNCTION assign_person_group();

INSERT INTO person (last_name, first_name, middle_name, birth_date, gender, address, phone, email)
VALUES ('Иванов', 'Иван', 'Петрович', '1990-01-01', 'М', 'Москва', '+7(999)123-45-67', 'ivan@mail.ru');

INSERT INTO person (last_name, first_name, middle_name, birth_date, gender, address, phone, email)
VALUES ('Иванов', 'Иван', 'Петрович', '1992-01-11', 'Ж', 'Москва', '+7(999)123-45-67', 'ivan@yandex.ru');

SELECT id, group_id, last_name, first_name, phone, email FROM person;
SELECT * FROM person_group;

--Реализация с персистентностью

--Что-то вроде таблицы коммитов
CREATE TABLE change_set (
  id BIGSERIAL PRIMARY KEY,
  authored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  author TEXT,
  reason TEXT
);

--Функция, возможно потребуется для бэка
CREATE OR REPLACE FUNCTION open_change_set(p_author TEXT, p_reason TEXT)
RETURNS BIGINT LANGUAGE SQL AS $$
  INSERT INTO change_set(author, reason) VALUES (p_author, p_reason) RETURNING id;
$$;

-- текущее состояние, по одной строке на группу
ALTER TABLE person
  ADD COLUMN change_id BIGINT REFERENCES change_set(id),
  ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT true;

-- история предыдущих версий
CREATE TABLE person_history (
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
CREATE VIEW person_current AS
SELECT *
FROM person
WHERE is_current = true;

--Запрет обновления у удаления(вдруг захочет проверить)
CREATE OR REPLACE FUNCTION forbid_direct_write()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- если UPDATE/DELETE вызван другим триггером, разрешаем
  IF pg_trigger_depth() > 1 THEN
    RETURN NULL;
  END IF;

  RAISE EXCEPTION 'Direct % on % is forbidden; use INSERT with triggers', TG_OP, TG_TABLE_NAME;
END;
$$;

-- CREATE TRIGGER t_no_update_person
--   BEFORE UPDATE OR DELETE ON person
--   FOR EACH STATEMENT EXECUTE FUNCTION forbid_direct_write();

--Функция и триггер на персистентность
CREATE OR REPLACE FUNCTION version_person_after_insert()
RETURNS TRIGGER AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_prev RECORD;
BEGIN
  -- если была актуальная запись для этой группы — закрываем её
  SELECT *
  INTO v_prev
  FROM person
  WHERE group_id = NEW.group_id AND is_current = true AND id <> NEW.id
  LIMIT 1;

  IF FOUND THEN
    INSERT INTO person_history(
      group_id, change_id,
      last_name, first_name, middle_name, birth_date, gender, address, phone, email,
      valid_from, valid_to
    )
    VALUES (
      v_prev.group_id, COALESCE(NEW.change_id, v_prev.change_id),
      v_prev.last_name, v_prev.first_name, v_prev.middle_name, v_prev.birth_date, v_prev.gender,
      v_prev.address, v_prev.phone, v_prev.email,
      v_prev.created_at, v_now
    );

    UPDATE person
    SET is_current = false
    WHERE id = v_prev.id;
  END IF;

  -- новая строка остаётся текущей; created_at/ change_id приходят от приложения/по умолчанию
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- CREATE TRIGGER trg_version_person_after_insert
-- AFTER INSERT ON person
-- FOR EACH ROW
-- EXECUTE FUNCTION version_person_after_insert();

--Чтение на момент времени T
CREATE OR REPLACE FUNCTION person_as_of(p_group_id INT, t TIMESTAMPTZ)
RETURNS TABLE(
  group_id INT,
  last_name  VARCHAR,
  first_name VARCHAR,
  middle_name VARCHAR,
  birth_date DATE,
  gender CHAR(1),
  address TEXT,
  phone VARCHAR(20),
  email VARCHAR(255)
) LANGUAGE sql AS $$
  -- 1) если текущая запись создана не позже t — берём её
  SELECT p.group_id, p.last_name, p.first_name, p.middle_name, p.birth_date, p.gender,
         p.address, p.phone, p.email
  FROM person p
  WHERE p.group_id = p_group_id AND p.is_current = true AND p.created_at <= t

  UNION ALL

  -- 2) иначе берём прошлую, которая перекрывает момент t
  SELECT h.group_id, h.last_name, h.first_name, h.middle_name, h.birth_date, h.gender,
         h.address, h.phone, h.email
  FROM person_history h
  WHERE h.group_id = p_group_id
    AND h.valid_from <= t AND t < h.valid_to
  LIMIT 1;
$$;


-- текущее состояние и связь с группой
CREATE INDEX i_person_current ON person(is_current) WHERE is_current;
CREATE INDEX i_person_group   ON person(group_id);

-- для поиска (по установленным правилам)
CREATE INDEX i_person_match
  ON person (gender, first_name, COALESCE(middle_name,''), last_name)
  WHERE is_current;

-- быстрый поиск по контактам (точное совпадение)
CREATE INDEX i_person_phone  ON person(phone)  WHERE is_current;
CREATE INDEX i_person_email  ON person(email)  WHERE is_current;

-- для истории (диапазоны)
CREATE INDEX i_hist_group_from_to ON person_history (group_id, valid_from, valid_to);

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

--Функция для витрины с гибким поиском(как раз для API)
CREATE OR REPLACE FUNCTION person_vitrine_search(
  p_last_name   VARCHAR DEFAULT NULL,
  p_first_name  VARCHAR DEFAULT NULL,
  p_middle_name VARCHAR DEFAULT NULL,
  p_address     TEXT    DEFAULT NULL,
  p_phone       VARCHAR DEFAULT NULL,
  p_email       VARCHAR DEFAULT NULL,
  p_limit       INT     DEFAULT 100,
  p_offset      INT     DEFAULT 0
)
RETURNS TABLE(
  group_id INT,
  last_name VARCHAR, first_name VARCHAR, middle_name VARCHAR,
  birth_date DATE, gender CHAR(1),
  address TEXT, phone VARCHAR, email VARCHAR
) LANGUAGE sql AS $$
  SELECT
    group_id, last_name, first_name, middle_name,
    birth_date, gender,
    address, phone, email
  FROM person_vitrine
  WHERE
    (p_last_name   IS NULL OR last_name   = p_last_name)
    AND (p_first_name  IS NULL OR first_name  = p_first_name)
    AND (p_middle_name IS NULL OR COALESCE(middle_name,'') = COALESCE(p_middle_name,''))
    AND (p_phone    IS NULL OR phone  = p_phone)
    AND (p_email    IS NULL OR email  = p_email)
    AND (p_address  IS NULL OR address = p_address)  -- при желании заменить на ILIKE/pg_trgm
  ORDER BY group_id
  LIMIT p_limit OFFSET p_offset;
$$;


--Демонстрационный скрипт
-- одна «партия» вставок помечена этим change_id
WITH cs AS (
  INSERT INTO change_set(author, reason)
  VALUES ('demo', 'initial demo batch')
  RETURNING id
)

-- 2) Иванов Иван Петрович — первая запись (создаст НОВУЮ группу #1)
INSERT INTO person (group_id, change_id,
  last_name, first_name, middle_name, birth_date, gender,
  address, phone, email
)
SELECT NULL, cs.id,
  'Иванов','Иван','Петрович','1990-01-01','М',
  'г. Москва, ул. Тверская, д.1', '+7(999)123-45-67', 'ivan@mail.ru'
FROM cs;

-- 3) Тот же человек: совпадают ФИО/пол и телефон -> попадёт в ТУ ЖЕ группу #1,
-- а предыдущая «текущая» версия уедет в person_history.
WITH cs AS (
  INSERT INTO change_set(author, reason)
  VALUES ('demo', 'update phone/email/address for Ivanov') RETURNING id
)
INSERT INTO person (group_id, change_id,
  last_name, first_name, middle_name, birth_date, gender,
  address, phone, email
)
SELECT NULL, cs.id,
  'Иванов','Иван','Петрович','1990-01-01','М',
  'г. Москва, Новая пл., д.2', '+7(999)123-45-67', 'ivan@yandex.ru'
FROM cs;

-- 4) Похожая запись, но НЕТ общих контактов (адрес/тел/почта все другие).
-- Для мужчин фамилия обязательна к совпадению — она совпадает,
-- но т.к. контактов общих нет, это ДРУГОЙ человек -> создаст группу #2
WITH cs AS (
  INSERT INTO change_set(author, reason)
  VALUES ('demo', 'another Ivanov with no shared contacts') RETURNING id
)
INSERT INTO person (group_id, change_id,
  last_name, first_name, middle_name, birth_date, gender,
  address, phone, email
)
SELECT NULL, cs.id,
  'Иванов','Иван','Петрович','1990-01-01','М',
  'г. Санкт-Петербург, Невский пр., д.10', '+7(999)888-77-66', 'ivan.other@mail.ru'
FROM cs;

-- 5) Женский кейс: фамилия может отличаться, но есть общий e-mail -> ТА ЖЕ группа.
-- Сначала создадим новую женщину (создаст группу #3):
WITH cs AS (
  INSERT INTO change_set(author, reason)
  VALUES ('demo', 'female base') RETURNING id
)
INSERT INTO person (group_id, change_id,
  last_name, first_name, middle_name, birth_date, gender,
  address, phone, email
)
SELECT NULL, cs.id,
  'Петрова','Анна',NULL,'1995-05-05','Ж',
  'г. Казань, Кремлёвская, д.5', '+7(900)111-22-33', 'anna@gmail.com'
FROM cs;

-- Теперь новая запись с ДРУГОЙ фамилией, тем же email -> попадёт в группу #3,
-- а предыдущая версия станет исторической.
WITH cs AS (
  INSERT INTO change_set(author, reason)
  VALUES ('demo', 'female last name changed, same email') RETURNING id
)
INSERT INTO person (group_id, change_id,
  last_name, first_name, middle_name, birth_date, gender,
  address, phone, email
)
SELECT NULL, cs.id,
  'Смирнова','Анна',NULL,'1995-05-05','Ж',
  'г. Казань, Баумана, д.7', '+7(900)111-22-33', 'anna@gmail.com'
FROM cs;

--Просмотр текущих версий по людям
SELECT id, group_id, last_name, first_name, middle_name, gender, address, phone, email, created_at, change_id
FROM person
WHERE is_current = true
ORDER BY group_id, id;

--История версий
SELECT group_id, last_name, first_name, middle_name, gender,
       address, phone, email, valid_from, valid_to, change_id
FROM person_history
ORDER BY group_id, valid_from;

-- всего групп
SELECT COUNT(*) AS groups_total FROM person_group;

-- текущие записи по группам
SELECT group_id, COUNT(*) AS current_rows
FROM person WHERE is_current = true
GROUP BY group_id ORDER BY group_id;

-- сколько прошлых версий по каждой группе
SELECT group_id, COUNT(*) AS history_rows
FROM person_history
GROUP BY group_id ORDER BY group_id;

--Просмотреть за интервал
SELECT * FROM person_as_of(1, now() - interval '5 minutes');

-- Текущее состояние той же группы
SELECT * FROM person_as_of(1, now());

--Тестовая вставка на вторую группу
WITH cs AS (
  INSERT INTO change_set(author, reason)
  VALUES ('demo', 'update second male') RETURNING id
)
INSERT INTO person (group_id, change_id,
  last_name, first_name, middle_name, birth_date, gender,
  address, phone, email
)
SELECT NULL, cs.id,
  'Иванов','Иван','Петрович','1990-01-01','М',
  'СПб, Литейный, д.3', '+7(999)888-77-86', 'ivan.other@new.ru'
FROM cs;

SELECT group_id, is_current, address, email, created_at
FROM person
WHERE group_id = 2
ORDER BY created_at;

SELECT group_id, address, email, valid_from, valid_to
FROM person_history
WHERE group_id = 2
ORDER BY valid_from;

--Примеры использования функции для витрины
SELECT * FROM person_vitrine_search(p_last_name=>'Иванов');
SELECT * FROM person_vitrine_search(p_phone=>'+7(999)888-77-66');
SELECT * FROM person_vitrine_search(p_email=>'anna@gmail.com');

-- Если что-то пошло не так, это сотрёт все данные
TRUNCATE TABLE person_history, person, person_group, change_set
RESTART IDENTITY CASCADE;

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