import sqlite3

# Укажите путь к вашей базе
conn = sqlite3.connect('wishes.db')
c = conn.cursor()

# Пример: удалить пожелание с id = 5
# c.execute("DELETE FROM wishes WHERE id = ?", (5,))


c.execute("DELETE FROM wishes")

conn.commit()
conn.close()
print("Готово!")
