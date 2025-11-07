# -----------------------------------------------------------------------------
# EXPERIENCIAS EXPY FEST - GESTOR DE FILAS - app.py (CON POSTGRESQL)
# -----------------------------------------------------------------------------
# Versión mejorada con soporte para PostgreSQL (Railway) y SQLite (local)
# -----------------------------------------------------------------------------

import os
from flask import Flask, render_template, request, redirect, url_for, flash

# --- Configuración de la Aplicación ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una-clave-secreta-muy-segura-dev')

# Detectar si estamos en Railway (tiene DATABASE_URL) o local (SQLite)
DATABASE_URL = os.environ.get('DATABASE_URL')
USE_POSTGRES = DATABASE_URL is not None

# --- Funciones de la Base de Datos ---

def get_db_connection():
    """Crea una conexión a la base de datos (PostgreSQL o SQLite)."""
    try:
        if USE_POSTGRES:
            # PostgreSQL (producción en Railway)
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            # Esto hace que las filas se comporten como diccionarios
            conn.cursor_factory = psycopg2.extras.RealDictCursor
        else:
            # SQLite (desarrollo local)
            import sqlite3
            conn = sqlite3.connect('event_attractions.db')
            conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Error de base de datos: {e}")
        raise

def execute_query(conn, query, params=None):
    """Ejecuta una query compatible con ambas bases de datos."""
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        # PostgreSQL usa %s como placeholder
        query = query.replace('?', '%s')
    
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    
    return cursor

def init_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if USE_POSTGRES:
        # PostgreSQL
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attractions (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                duration_minutes INTEGER DEFAULT 5
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id SERIAL PRIMARY KEY,
                attraction_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attraction_id) REFERENCES attractions (id)
            )
        """)
        print("Base de datos PostgreSQL inicializada ✓")
    else:
        # SQLite
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                duration_minutes INTEGER DEFAULT 5
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attraction_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attraction_id) REFERENCES attractions (id)
            )
        """)
        print("Base de datos SQLite inicializada ✓")

    conn.commit()
    conn.close()


# --- Rutas de la Aplicación ---

@app.route('/')
def index():
    """Página principal: Muestra todas las experiencias y el número de personas en fila."""
    conn = get_db_connection()
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
    cursor = execute_query(conn, query)
    attractions = cursor.fetchall()
    conn.close()
    return render_template('index.html', attractions=attractions)

@app.route('/attraction/<int:attraction_id>')
def attraction_detail(attraction_id):
    """Página de detalle: Muestra la información de una experiencia y su fila."""
    conn = get_db_connection()
    
    cursor = execute_query(conn, 'SELECT * FROM attractions WHERE id = ?', (attraction_id,))
    attraction = cursor.fetchone()
    
    cursor = execute_query(conn, 'SELECT * FROM queue WHERE attraction_id = ? ORDER BY timestamp', (attraction_id,))
    queue = cursor.fetchall()
    
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
            execute_query(conn, 
                'INSERT INTO attractions (name, description, duration_minutes) VALUES (?, ?, ?)', 
                (name, description, duration_minutes))
            conn.commit()
            flash(f'Experiencia "{name}" creada exitosamente (duración: {duration_minutes} min)', 'success')
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                flash(f'Error: El nombre de la experiencia "{name}" ya existe.', 'error')
            else:
                flash(f'Error al crear la experiencia: {str(e)}', 'error')
        finally:
            conn.close()

    return redirect(url_for('index'))

@app.route('/add_to_queue/<int:attraction_id>', methods=['POST'])
def add_to_queue(attraction_id):
    """Procesa el formulario para añadir una persona a la fila."""
    person_name = request.form.get('person_name', '').strip()

    if not person_name:
        flash('El nombre no puede estar vacío', 'error')
        return redirect(url_for('attraction_detail', attraction_id=attraction_id))
    
    if len(person_name) < 2:
        flash('El nombre debe tener al menos 2 caracteres', 'error')
        return redirect(url_for('attraction_detail', attraction_id=attraction_id))

    conn = get_db_connection()
    
    cursor = execute_query(conn, 'SELECT name, duration_minutes FROM attractions WHERE id = ?', (attraction_id,))
    attraction = cursor.fetchone()
    
    if not attraction:
        conn.close()
        flash('Experiencia no encontrada', 'error')
        return redirect(url_for('index'))
    
    cursor = execute_query(conn, 'SELECT COUNT(*) as count FROM queue WHERE attraction_id = ?', (attraction_id,))
    queue_count = cursor.fetchone()['count']
    
    execute_query(conn, 'INSERT INTO queue (attraction_id, person_name) VALUES (?, ?)', (attraction_id, person_name))
    conn.commit()
    conn.close()
    
    new_queue_count = queue_count + 1
    estimated_wait = new_queue_count * (attraction['duration_minutes'] or 5)
    
    flash(f'{person_name} añadido a la fila. Tiempo estimado: {estimated_wait} minutos', 'success')

    return redirect(url_for('attraction_detail', attraction_id=attraction_id))

@app.route('/next_person/<int:queue_id>', methods=['POST'])
def next_person(queue_id):
    """Elimina a la persona de la fila (simula que ya pasó)."""
    conn = get_db_connection()
    
    cursor = execute_query(conn, 'SELECT attraction_id FROM queue WHERE id = ?', (queue_id,))
    queue_item = cursor.fetchone()

    if queue_item:
        attraction_id = queue_item['attraction_id']
        execute_query(conn, 'DELETE FROM queue WHERE id = ?', (queue_id,))
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
    cursor = execute_query(conn, 'SELECT * FROM attractions WHERE id = ?', (attraction_id,))
    attraction = cursor.fetchone()
    
    if attraction is None:
        conn.close()
        return "Experiencia no encontrada", 404
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        duration_minutes = int(request.form.get('duration_minutes', 5))
        
        if name:
            try:
                execute_query(conn, 
                    'UPDATE attractions SET name = ?, description = ?, duration_minutes = ? WHERE id = ?', 
                    (name, description, duration_minutes, attraction_id))
                conn.commit()
                conn.close()
                flash(f'Experiencia "{name}" actualizada exitosamente (duración: {duration_minutes} min)', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                    flash(f'Error: El nombre de la experiencia "{name}" ya existe.', 'error')
                else:
                    flash(f'Error: {str(e)}', 'error')
                conn.close()
                return render_template('edit_attraction.html', attraction=attraction)
    
    conn.close()
    return render_template('edit_attraction.html', attraction=attraction)

@app.route('/delete_attraction/<int:attraction_id>', methods=['POST'])
def delete_attraction(attraction_id):
    """Elimina una experiencia y todas las personas en su fila."""
    conn = get_db_connection()
    
    cursor = execute_query(conn, 'SELECT * FROM attractions WHERE id = ?', (attraction_id,))
    attraction = cursor.fetchone()
    
    if attraction is None:
        conn.close()
        flash('Experiencia no encontrada', 'error')
        return redirect(url_for('index'))
    
    execute_query(conn, 'DELETE FROM queue WHERE attraction_id = ?', (attraction_id,))
    execute_query(conn, 'DELETE FROM attractions WHERE id = ?', (attraction_id,))
    conn.commit()
    conn.close()
    
    flash('Experiencia eliminada exitosamente', 'success')
    return redirect(url_for('index'))

@app.route('/clear_queue/<int:attraction_id>', methods=['POST'])
def clear_queue(attraction_id):
    """Vacía completamente la fila de una experiencia."""
    conn = get_db_connection()
    
    cursor = execute_query(conn, 'SELECT * FROM attractions WHERE id = ?', (attraction_id,))
    attraction = cursor.fetchone()
    
    if attraction is None:
        conn.close()
        flash('Experiencia no encontrada', 'error')
        return redirect(url_for('index'))
    
    execute_query(conn, 'DELETE FROM queue WHERE attraction_id = ?', (attraction_id,))
    conn.commit()
    conn.close()
    
    flash('Fila vaciada exitosamente', 'success')
    return redirect(url_for('attraction_detail', attraction_id=attraction_id))

# --- Inicialización de la Base de Datos ---
init_db()

# --- Inicio de la Aplicación ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
