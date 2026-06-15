// foundry-template: vitepress-config v1
import { defineConfig } from 'vitepress'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const sidebarPath = fileURLToPath(new URL('./sidebar.generated.json', import.meta.url))
const sidebar = existsSync(sidebarPath)
  ? JSON.parse(readFileSync(sidebarPath, 'utf-8'))
  : []

const sitePath = fileURLToPath(new URL('./site.json', import.meta.url))
const site = existsSync(sitePath)
  ? JSON.parse(readFileSync(sitePath, 'utf-8'))
  : {}

export default defineConfig({
  title: site.title ?? 'Docs',
  description: site.description ?? 'Project documentation',
  srcExclude: ['**/node_modules/**', 'README.md'],
  ignoreDeadLinks: true,
  themeConfig: {
    sidebar,
    nav: [{ text: 'Start here', link: '/' }],
  },
})
