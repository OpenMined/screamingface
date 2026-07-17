import { describe, it, expect } from 'vitest'

import { mount } from '@vue/test-utils'
import App from '@/App.vue'

describe('App', () => {
  it('mounts and renders the layout shell', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          TheNavbar: true,
          RouterView: true,
        },
      },
    })
    expect(wrapper.find('main').exists()).toBe(true)
  })
})
