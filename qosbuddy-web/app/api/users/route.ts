import { NextRequest, NextResponse } from 'next/server'
import bcrypt from 'bcryptjs'
import { getUsers, createUser, updateUser, deleteUser, User } from '@/lib/db'

// GET all users
export async function GET() {
  try {
    const users = await getUsers()
    // Remove passwords from response
    const usersWithoutPasswords = users.map(({ password, ...user }) => user)
    return NextResponse.json(usersWithoutPasswords)
  } catch (error) {
    console.error('Get users error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch users' },
      { status: 500 }
    )
  }
}

// POST create new user
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { email, password, name, role, department, avatar, notifications_enabled } = body
    
    if (!email || !password || !name) {
      return NextResponse.json(
        { error: 'Email, password, and name are required' },
        { status: 400 }
      )
    }
    
    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10)
    
    const userData: Omit<User, 'id' | 'created_at' | 'last_login'> = {
      email,
      password: hashedPassword,
      name,
      role: role || 'viewer',
      department: department || '',
      avatar: avatar || null,
      notifications_enabled: notifications_enabled !== false
    }
    
    const id = await createUser(userData)
    
    return NextResponse.json(
      { success: true, id, message: 'User created successfully' },
      { status: 201 }
    )
  } catch (error) {
    console.error('Create user error:', error)
    return NextResponse.json(
      { error: 'Failed to create user' },
      { status: 500 }
    )
  }
}

// PATCH update user
export async function PATCH(req: NextRequest) {
  try {
    const { id, ...updates } = await req.json()
    
    if (!id) {
      return NextResponse.json(
        { error: 'User ID is required' },
        { status: 400 }
      )
    }
    
    // If password is being updated, hash it
    if (updates.password) {
      updates.password = await bcrypt.hash(updates.password, 10)
    }
    
    await updateUser(id, updates)
    
    return NextResponse.json({
      success: true,
      message: 'User updated successfully'
    })
  } catch (error) {
    console.error('Update user error:', error)
    return NextResponse.json(
      { error: 'Failed to update user' },
      { status: 500 }
    )
  }
}

// DELETE user
export async function DELETE(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const id = searchParams.get('id')
    
    if (!id) {
      return NextResponse.json(
        { error: 'User ID is required' },
        { status: 400 }
      )
    }
    
    await deleteUser(parseInt(id))
    
    return NextResponse.json({
      success: true,
      message: 'User deleted successfully'
    })
  } catch (error) {
    console.error('Delete user error:', error)
    return NextResponse.json(
      { error: 'Failed to delete user' },
      { status: 500 }
    )
  }
}
