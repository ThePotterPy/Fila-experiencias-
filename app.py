# -----------------------------------------------------------------------------
# EXPERIENCIAS EXPY FEST - GESTOR DE FILAS - app.py
# -----------------------------------------------------------------------------
# Este script crea una aplicación web local para gestionar las filas de
# varias experiencias en el Festival de Experiencias Inmersivas Expy Fest.
#
# Para ejecutarlo:
# 1. Asegúrate de tener Python instalado.
# 2. Instala Flask: pip install Flask
# 3. Guarda este archivo como 'app.py'.
# 4. Crea una carpeta llamada 'templates' en el mismo directorio.
# 5. Guarda los archivos 'index.html' y 'attraction.html' dentro de la carpeta 'templates'.
# 6. Ejecuta el script desde tu terminal: python app.py
# 7. Abre tu navegador y ve a http://127.0.0.1:5000
#
# Otros voluntarios en la misma red Wi-Fi podrán acceder usando la IP local
# de tu computadora (ej: http://192.168.1.10:5000).
# -----------------------------------------------------------------------------

import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash

# --- Configuración de la Aplicación ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'una-clave-secreta-muy-segura' # Necesario para el funcionamiento interno de Flask

DATABASE_FILE = 'event_attractions.db'

# --- Funciones de la Base de Datos ---

def get_db_connection():
    """Crea una conexión a la base de datos."""
    conn = sqlite3.connect(DATABASE_FILE)
    # Permite acceder a las columnas por su nombre (ej: row['name'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verificar si las tablas existen
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attractions'")
    if not cursor.fetchone():
        print("Creando la base de datos por primera vez...")
        
        # Tabla para las experiencias
        cursor.execute('''
            CREATE TABLE attractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                duration_minutes INTEGER DEFAULT 5
            )
        ''')

        # Tabla para las personas en la fila (queue)
        cursor.execute('''
            CREATE TABLE queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attraction_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attraction_id) REFERENCES attractions (id)
            )
        ''')
        
        print("Base de datos creada exitosamente.")
    else:
        # Verificar si la columna duration_minutes existe
        cursor.execute("PRAGMA table_info(attractions)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'duration_minutes' not in columns:
            print("Actualizando base de datos existente...")
            cursor.execute('ALTER TABLE attractions ADD COLUMN duration_minutes INTEGER DEFAULT 5')
            print("Base de datos actualizada exitosamente.")

    conn.commit()
    conn.close()


# --- Rutas de la Aplicación (Las "Páginas") ---

@app.route('/')
def index():
    """Página principal: Muestra todas las experiencias y el número de personas en fila."""
    conn = get_db_connection()
    # Consulta que une las experiencias con la cuenta de personas en su fila
    query = """
        SELECT
            a.id,
            a.name,
            a.description,
            a.duration_minutes,
            COUNT(q.id) as queue_count,
            (COUNT(q.id) * a.duration_minutes) as estimated_wait_minutes
        FROM
            attractions a
        LEFT JOIN
            queue q ON a.id = q.attraction_id
        GROUP BY
            a.id, a.name, a.description, a.duration_minutes
        ORDER BY
            a.name;
    """
    attractions = conn.execute(query).fetchall()
    conn.close()
    return render_template('index.html', attractions=attractions)

@app.route('/attraction/<int:attraction_id>')
def attraction_detail(attraction_id):
    """Página de detalle: Muestra la información de una experiencia y su fila."""
    conn = get_db_connection()
    # Obtener datos de la experiencia
    attraction = conn.execute('SELECT * FROM attractions WHERE id = ?', (attraction_id,)).fetchone()
    # Obtener la lista de personas en la fila, ordenadas por llegada
    queue = conn.execute('SELECT * FROM queue WHERE attraction_id = ? ORDER BY timestamp', (attraction_id,)).fetchall()
    conn.close()

    if attraction is None:
        return "Experiencia no encontrada", 404

    return render_template('attraction.html', attraction=attraction, queue=queue)

@app.route('/add_attraction', methods=['POST'])
def add_attraction():
    """Procesa el formulario para añadir una nueva experiencia."""
    name = request.form['name']
    description = request.form['description']
    duration_minutes = int(request.form.get('duration_minutes', 5))

    if name:
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO attractions (name, description, duration_minutes) VALUES (?, ?, ?)', 
                        (name, description, duration_minutes))
            conn.commit()
            flash(f'Experiencia "{name}" creada exitosamente (duración: {duration_minutes} min)', 'success')
        except sqlite3.IntegrityError:
            # Manejar el caso de que el nombre ya exista
            flash(f'Error: El nombre de la experiencia "{name}" ya existe.', 'error')
        finally:
            conn.close()

    return redirect(url_for('index'))

@app.route('/add_to_queue/<int:attraction_id>', methods=['POST'])
def add_to_queue(attraction_id):
    """Procesa el formulario para añadir una persona a la fila."""
    person_name = request.form['person_name']

    if person_name:
        conn = get_db_connection()
        
        # Obtener información de la experiencia para calcular tiempo estimado
        attraction = conn.execute('SELECT name, duration_minutes FROM attractions WHERE id = ?', (attraction_id,)).fetchone()
        
        # Contar personas en la fila antes de añadir
        queue_count = conn.execute('SELECT COUNT(*) as count FROM queue WHERE attraction_id = ?', (attraction_id,)).fetchone()['count']
        
        conn.execute('INSERT INTO queue (attraction_id, person_name) VALUES (?, ?)', (attraction_id, person_name))
        conn.commit()
        conn.close()
        
        # Calcular tiempo estimado después de añadir
        new_queue_count = queue_count + 1
        estimated_wait = new_queue_count * (attraction['duration_minutes'] or 5)
        
        flash(f'{person_name} añadido a la fila. Tiempo estimado: {estimated_wait} minutos', 'success')

    return redirect(url_for('attraction_detail', attraction_id=attraction_id))

@app.route('/next_person/<int:queue_id>', methods=['POST'])
def next_person(queue_id):
    """Elimina a la persona de la fila (simula que ya pasó)."""
    conn = get_db_connection()
    # Primero, necesitamos saber a qué página de atracción redirigir
    queue_item = conn.execute('SELECT attraction_id FROM queue WHERE id = ?', (queue_id,)).fetchone()

    if queue_item:
        attraction_id = queue_item['attraction_id']
        conn.execute('DELETE FROM queue WHERE id = ?', (queue_id,))
        conn.commit()
        conn.close()
        flash('Persona procesada', 'success')
        return redirect(url_for('attraction_detail', attraction_id=attraction_id))
    else:
        conn.close()
        return redirect(url_for('index'))

@app.route('/edit_attraction/<int:attraction_id>', methods=['GET', 'POST'])
def edit_attraction(attraction_id):
    """Página para editar una experiencia existente."""
    conn = get_db_connection()
    attraction = conn.execute('SELECT * FROM attractions WHERE id = ?', (attraction_id,)).fetchone()
    
    if attraction is None:
        conn.close()
        return "Experiencia no encontrada", 404
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        duration_minutes = int(request.form.get('duration_minutes', 5))
        
        if name:
            try:
                conn.execute('UPDATE attractions SET name = ?, description = ?, duration_minutes = ? WHERE id = ?', 
                           (name, description, duration_minutes, attraction_id))
                conn.commit()
                conn.close()
                flash(f'Experiencia "{name}" actualizada exitosamente (duración: {duration_minutes} min)', 'success')
                return redirect(url_for('index'))
            except sqlite3.IntegrityError:
                flash(f'Error: El nombre de la experiencia "{name}" ya existe.', 'error')
                conn.close()
                return render_template('edit_attraction.html', attraction=attraction)
    
    conn.close()
    return render_template('edit_attraction.html', attraction=attraction)

@app.route('/delete_attraction/<int:attraction_id>', methods=['POST'])
def delete_attraction(attraction_id):
    """Elimina una experiencia y todas las personas en su fila."""
    conn = get_db_connection()
    
    # Verificar que la experiencia existe
    attraction = conn.execute('SELECT * FROM attractions WHERE id = ?', (attraction_id,)).fetchone()
    if attraction is None:
        conn.close()
        flash('Experiencia no encontrada', 'error')
        return redirect(url_for('index'))
    
    # Eliminar todas las personas de la fila (CASCADE automático por FOREIGN KEY)
    conn.execute('DELETE FROM queue WHERE attraction_id = ?', (attraction_id,))
    # Eliminar la experiencia
    conn.execute('DELETE FROM attractions WHERE id = ?', (attraction_id,))
    conn.commit()
    conn.close()
    
    flash('Experiencia eliminada exitosamente', 'success')
    return redirect(url_for('index'))

@app.route('/clear_queue/<int:attraction_id>', methods=['POST'])
def clear_queue(attraction_id):
    """Vacía completamente la fila de una experiencia."""
    conn = get_db_connection()
    
    # Verificar que la experiencia existe
    attraction = conn.execute('SELECT * FROM attractions WHERE id = ?', (attraction_id,)).fetchone()
    if attraction is None:
        conn.close()
        flash('Experiencia no encontrada', 'error')
        return redirect(url_for('index'))
    
    # Eliminar todas las personas de la fila
    conn.execute('DELETE FROM queue WHERE attraction_id = ?', (attraction_id,))
    conn.commit()
    conn.close()
    
    flash('Fila vaciada exitosamente', 'success')
    return redirect(url_for('attraction_detail', attraction_id=attraction_id))

# --- Inicio de la Aplicación ---
if __name__ == '__main__':
    init_db()  # Asegurarse de que la base de datos esté lista
    # host='0.0.0.0' hace la app visible en tu red local
    app.run(host='0.0.0.0', port=5000, debug=True)
