import mysql from 'mysql2/promise'

// XAMPP MySQL default configuration
const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '3306'),
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || 'qosbuddy',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
}

// Create connection pool
const pool = mysql.createPool(dbConfig)

export interface User {
  id: number
  email: string
  password: string
  name: string
  role: 'admin' | 'engineer' | 'viewer'
  department: string
  avatar: string | null
  notifications_enabled: boolean
  created_at: Date
  last_login: Date | null
}

export interface IncidentReport {
  id: number
  event_id: string
  cell_id: string
  severity: string
  status: string
  created_by: number
  created_at: Date
  pdf_path: string | null
}

// User operations
export async function getUsers(): Promise<User[]> {
  const [rows] = await pool.execute('SELECT * FROM users ORDER BY created_at DESC')
  return rows as User[]
}

export async function getUserByEmail(email: string): Promise<User | null> {
  const [rows] = await pool.execute('SELECT * FROM users WHERE email = ?', [email])
  const users = rows as User[]
  return users.length > 0 ? users[0] : null
}

export async function getUserById(id: number): Promise<User | null> {
  const [rows] = await pool.execute('SELECT * FROM users WHERE id = ?', [id])
  const users = rows as User[]
  return users.length > 0 ? users[0] : null
}

export async function createUser(user: Omit<User, 'id' | 'created_at' | 'last_login'>): Promise<number> {
  const [result] = await pool.execute(
    'INSERT INTO users (email, password, name, role, department, avatar, notifications_enabled) VALUES (?, ?, ?, ?, ?, ?, ?)',
    [user.email, user.password, user.name, user.role, user.department, user.avatar, user.notifications_enabled]
  )
  return (result as mysql.ResultSetHeader).insertId
}

export async function updateUser(id: number, updates: Partial<User>): Promise<void> {
  const fields = Object.keys(updates).filter(k => k !== 'id')
  if (fields.length === 0) return
  
  const setClause = fields.map(f => `${f} = ?`).join(', ')
  const values = fields.map(f => updates[f as keyof User])
  
  await pool.execute(`UPDATE users SET ${setClause} WHERE id = ?`, [...values, id])
}

export async function deleteUser(id: number): Promise<void> {
  await pool.execute('DELETE FROM users WHERE id = ?', [id])
}

export async function updateLastLogin(id: number): Promise<void> {
  await pool.execute('UPDATE users SET last_login = NOW() WHERE id = ?', [id])
}

// Initialize database tables
export async function initDatabase(): Promise<void> {
  const connection = await pool.getConnection()
  try {
    // Create users table
    await connection.execute(`
      CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        role ENUM('admin', 'engineer', 'viewer') DEFAULT 'viewer',
        department VARCHAR(100) DEFAULT '',
        avatar VARCHAR(500) DEFAULT NULL,
        notifications_enabled BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP NULL
      )
    `)

    // Migration: Add password column if missing (for existing tables)
    try {
      await connection.execute(`ALTER TABLE users ADD COLUMN password VARCHAR(255) DEFAULT NULL`)
    } catch (e: any) {
      // Ignore if column already exists
      if (e.code !== 'ER_DUP_FIELDNAME') throw e
    }

    // Create reports table for tracking generated reports
    await connection.execute(`
      CREATE TABLE IF NOT EXISTS reports (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id VARCHAR(100) NOT NULL,
        cell_id VARCHAR(100) NOT NULL,
        severity VARCHAR(50) NOT NULL,
        status VARCHAR(50) DEFAULT 'open',
        created_by INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        pdf_path VARCHAR(500) DEFAULT NULL,
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
      )
    `)

    // Create default admin user if not exists
    const [existingAdmin] = await connection.execute(
      'SELECT id FROM users WHERE email = ?',
      ['admin@qosbuddy.com']
    )
    
    if ((existingAdmin as mysql.RowDataPacket[]).length === 0) {
      // Password: admin123 (hashed)
      await connection.execute(`
        INSERT INTO users (email, password, name, role, department)
        VALUES (?, ?, ?, ?, ?)
      `, ['admin@qosbuddy.com', '$2b$10$YourHashedPasswordHere', 'System Administrator', 'admin', 'IT'])
    }
  } finally {
    connection.release()
  }
}

export default pool
