import { vi } from 'vitest'

Object.defineProperty(navigator, 'clipboard', {
  configurable: true,
  value: {
    readText: vi.fn().mockResolvedValue('https://example.com/video'),
  },
})

