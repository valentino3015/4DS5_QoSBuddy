import jwt from 'jsonwebtoken'

const JWT_SECRET = process.env.JWT_SECRET || 'qosbuddy-secret-key-change-in-production'

export interface TokenPayload {
  userId: number
  email: string
  role: string
}

export function generateToken(payload: TokenPayload): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: '7d' })
}

export function verifyToken(token: string): TokenPayload | null {
  try {
    return jwt.verify(token, JWT_SECRET) as TokenPayload
  } catch {
    return null
  }
}
