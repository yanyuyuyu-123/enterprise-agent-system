// 权限判断：与后端 /auth/me 返回的 permissions 结构保持一致
// 权限码格式统一为 "resource:action"，例如 "purchase_order:read"

export function hasPermission(permissions, key) {
  const [resource, action] = String(key).split(':')
  return (permissions || []).some((item) => item.resource === resource && item.action === action)
}

export function hasAnyPermission(permissions, keys) {
  return (keys || []).some((key) => hasPermission(permissions, key))
}
