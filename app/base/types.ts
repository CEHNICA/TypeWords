export type ButtonProps = {
  keyboard?: string
  active?: boolean
  disabled?: boolean
  /** 禁用原因：禁用时鼠标悬停会弹出这段说明，避免「点了没反应」 */
  disabledReason?: string
  loading?: boolean
  size?: 'small' | 'normal' | 'large'
  type?: 'primary' | 'info' | 'orange' | 'text'
}
