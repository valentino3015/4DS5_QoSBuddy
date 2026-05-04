import { NextRequest, NextResponse } from 'next/server'
import bcrypt from 'bcryptjs'
import pool, { getUserByEmail, updateLastLogin, initDatabase } from '@/lib/db'
import { generateToken } from '@/lib/auth'

export async function POST(req: NextRequest) {
  try {
    // Ensure database is initialized
    await initDatabase()
    
    const { email, password } = await req.json()
    
    if (!email || !password) {
      return NextResponse.json(
        { error: 'Email and password are required' },
        { status: 400 }
      )
    }
    
    let user = await getUserByEmail(email)
    
    // Debug logging for troubleshooting
    console.log('Login attempt:', { email, userFound: !!user, hasPassword: !!user?.password, passwordValue: user?.password })
    
    // Fix: If admin user exists but has no password, reset it
    if (user && email === 'admin@qosbuddy.com' && !user.password) {
      console.log('Admin user found with empty password - resetting to default')
      await pool.execute(
        "UPDATE users SET password = '$2b$10$YourHashedPasswordHere' WHERE email = ?",
        [email]
      )
      // Re-fetch the user
      user = await getUserByEmail(email)
      console.log('Password reset complete:', { hasPassword: !!user?.password })
    }
    
    if (!user) {
      return NextResponse.json(
        { error: 'Invalid credentials' },
        { status: 401 }
      )
    }
    
    // For the default admin with placeholder password, allow any password
    // In production, this should be removed
    let isValid = false
    const userPassword = user.password || ''
    const isPlaceholder = userPassword.includes('YourHashedPasswordHere')
    
    console.log('Password check:', { isPlaceholder, passwordLength: userPassword.length })
    
    if (isPlaceholder) {
      isValid = password === 'admin123'
      console.log('Using placeholder password check:', isValid)
    } else {
      isValid = await bcrypt.compare(password, userPassword)
      console.log('Using bcrypt compare:', isValid)
    }
    
    if (!isValid) {
      return NextResponse.json(
        { error: 'Invalid credentials' },
        { status: 401 }
      )
    }
    
    // Update last login
    await updateLastLogin(user.id)
    
    // Generate JWT token
    const token = generateToken({
      userId: user.id,
      email: user.email,
      role: user.role
    })
    
    // Return user data (excluding password)
    const { password: _, ...userWithoutPassword } = user
    
    // Create response with cookie
    const response = NextResponse.json({
      success: true,
      user: userWithoutPassword
    })
    
    // Set auth cookie
    response.cookies.set('auth-token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7 // 7 days
    })
    
    return response
    
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
