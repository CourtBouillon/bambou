import sqlite3

from flask import current_app, g


def get_connection():
    if not hasattr(g, 'connection'):
        g.connection = sqlite3.connect(current_app.config['DB'])
        g.connection.row_factory = sqlite3.Row
        cursor = g.connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
    return g.connection


def close_connection():
    if hasattr(g, 'connection'):
        g.connection.close()
