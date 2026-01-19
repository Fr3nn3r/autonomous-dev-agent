# React Dark/Light Mode Theming with Animations

A complete guide to implementing dark/light mode theming with animated transitions, multiple color themes, and system preference detection.

## Overview

This setup provides:
- 3 color themes (Northern Lights, Default, Pink)
- 3 modes (Light, Dark, System)
- Smooth 500ms circular reveal animations on theme switch
- Automatic system preference detection
- Persistent theme state via localStorage

## Dependencies

```bash
npm install @space-man/react-theme-animation
```

## 1. Provider Setup

Wrap your app with the theme provider:

```tsx
// main.tsx or App.tsx
import { SpacemanThemeProvider, ThemeAnimationType } from '@space-man/react-theme-animation';

function App() {
  return (
    <SpacemanThemeProvider
      defaultTheme="system"
      defaultColorTheme="northern-lights"
      themes={['light', 'dark', 'system']}
      colorThemes={['northern-lights', 'default', 'pink']}
      animationType={ThemeAnimationType.CIRCLE}
      duration={500}
    >
      <YourApp />
    </SpacemanThemeProvider>
  );
}
```

### Provider Props

| Prop | Type | Description |
|------|------|-------------|
| `defaultTheme` | `string` | Initial mode: `'light'`, `'dark'`, or `'system'` |
| `defaultColorTheme` | `string` | Initial color theme ID |
| `themes` | `string[]` | Available modes |
| `colorThemes` | `string[]` | Available color theme IDs |
| `animationType` | `ThemeAnimationType` | Animation style (CIRCLE, FADE, etc.) |
| `duration` | `number` | Animation duration in milliseconds |

## 2. Hook Usage

Access theme state and controls anywhere in your app:

```tsx
import { useSpacemanTheme } from '@space-man/react-theme-animation';

function MyComponent() {
  const {
    theme,                    // Current mode: 'light' | 'dark' | 'system'
    darkMode,                 // Boolean: true if dark mode active
    colorTheme,               // Current color theme ID
    switchThemeFromElement,   // Switch mode with animation origin
    setColorTheme             // Change color scheme
  } = useSpacemanTheme();

  const handleModeChange = (mode: string, e: React.MouseEvent) => {
    // Animation originates from clicked element
    switchThemeFromElement(mode, e.currentTarget);
  };

  const handleColorChange = (themeId: string) => {
    setColorTheme(themeId);
  };

  return (
    <div>
      <button onClick={(e) => handleModeChange('dark', e)}>Dark Mode</button>
      <button onClick={() => handleColorChange('pink')}>Pink Theme</button>
    </div>
  );
}
```

## 3. Tailwind Configuration

```js
// tailwind.config.js
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  safelist: [
    "theme-northern-lights",
    "theme-default",
    "theme-pink",
    "dark"
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)"
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)"
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)"
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)"
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)"
        },
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)"
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)"
        },
        sidebar: {
          DEFAULT: "var(--sidebar)",
          foreground: "var(--sidebar-foreground)",
          primary: "var(--sidebar-primary)",
          "primary-foreground": "var(--sidebar-primary-foreground)",
          accent: "var(--sidebar-accent)",
          "accent-foreground": "var(--sidebar-accent-foreground)",
          border: "var(--sidebar-border)"
        }
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)"
      }
    }
  },
  plugins: []
}
```

## 4. CSS Variables

Define your color themes using CSS variables. Uses OKLch color space for perceptually uniform colors.

```css
/* index.css or globals.css */

/* Base layer with Tailwind */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ============================================
   BASE VARIABLES (fallback)
   ============================================ */
:root {
  --radius: 0.5rem;

  /* Light mode defaults */
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.145 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: oklch(0.577 0.245 27.325);
  --destructive-foreground: oklch(0.985 0 0);
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);

  /* Sidebar */
  --sidebar: oklch(0.985 0 0);
  --sidebar-foreground: oklch(0.145 0 0);
  --sidebar-primary: oklch(0.205 0 0);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.97 0 0);
  --sidebar-accent-foreground: oklch(0.205 0 0);
  --sidebar-border: oklch(0.922 0 0);
}

/* ============================================
   NORTHERN LIGHTS THEME
   Teal/cyan/purple accents
   ============================================ */
.theme-northern-lights {
  --background: oklch(0.985 0.002 247.839);
  --foreground: oklch(0.21 0.034 264.665);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.21 0.034 264.665);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.21 0.034 264.665);
  --primary: oklch(0.6487 0.1538 150.3071);
  --primary-foreground: oklch(0.985 0.002 247.839);
  --secondary: oklch(0.967 0.001 286.375);
  --secondary-foreground: oklch(0.21 0.034 264.665);
  --muted: oklch(0.967 0.001 286.375);
  --muted-foreground: oklch(0.552 0.016 285.938);
  --accent: oklch(0.967 0.001 286.375);
  --accent-foreground: oklch(0.21 0.034 264.665);
  --destructive: oklch(0.577 0.245 27.325);
  --destructive-foreground: oklch(0.985 0.002 247.839);
  --border: oklch(0.928 0.006 264.531);
  --input: oklch(0.928 0.006 264.531);
  --ring: oklch(0.6487 0.1538 150.3071);

  --sidebar: oklch(0.967 0.001 286.375);
  --sidebar-foreground: oklch(0.21 0.034 264.665);
  --sidebar-primary: oklch(0.6487 0.1538 150.3071);
  --sidebar-primary-foreground: oklch(0.985 0.002 247.839);
  --sidebar-accent: oklch(0.928 0.006 264.531);
  --sidebar-accent-foreground: oklch(0.21 0.034 264.665);
  --sidebar-border: oklch(0.928 0.006 264.531);
}

.theme-northern-lights.dark {
  --background: oklch(0.21 0.034 264.665);
  --foreground: oklch(0.985 0.002 247.839);
  --card: oklch(0.21 0.034 264.665);
  --card-foreground: oklch(0.985 0.002 247.839);
  --popover: oklch(0.21 0.034 264.665);
  --popover-foreground: oklch(0.985 0.002 247.839);
  --primary: oklch(0.6487 0.1538 150.3071);
  --primary-foreground: oklch(0.21 0.034 264.665);
  --secondary: oklch(0.293 0.042 264.052);
  --secondary-foreground: oklch(0.985 0.002 247.839);
  --muted: oklch(0.293 0.042 264.052);
  --muted-foreground: oklch(0.705 0.015 264.117);
  --accent: oklch(0.293 0.042 264.052);
  --accent-foreground: oklch(0.985 0.002 247.839);
  --destructive: oklch(0.704 0.191 22.216);
  --destructive-foreground: oklch(0.985 0.002 247.839);
  --border: oklch(0.293 0.042 264.052);
  --input: oklch(0.293 0.042 264.052);
  --ring: oklch(0.6487 0.1538 150.3071);

  --sidebar: oklch(0.25 0.038 264.358);
  --sidebar-foreground: oklch(0.985 0.002 247.839);
  --sidebar-primary: oklch(0.6487 0.1538 150.3071);
  --sidebar-primary-foreground: oklch(0.21 0.034 264.665);
  --sidebar-accent: oklch(0.293 0.042 264.052);
  --sidebar-accent-foreground: oklch(0.985 0.002 247.839);
  --sidebar-border: oklch(0.293 0.042 264.052);
}

/* ============================================
   DEFAULT THEME
   Grayscale neutral
   ============================================ */
.theme-default {
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.145 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: oklch(0.577 0.245 27.325);
  --destructive-foreground: oklch(0.985 0 0);
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);

  --sidebar: oklch(0.985 0 0);
  --sidebar-foreground: oklch(0.145 0 0);
  --sidebar-primary: oklch(0.205 0 0);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.97 0 0);
  --sidebar-accent-foreground: oklch(0.205 0 0);
  --sidebar-border: oklch(0.922 0 0);
}

.theme-default.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --card: oklch(0.145 0 0);
  --card-foreground: oklch(0.985 0 0);
  --popover: oklch(0.145 0 0);
  --popover-foreground: oklch(0.985 0 0);
  --primary: oklch(0.985 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --secondary: oklch(0.269 0 0);
  --secondary-foreground: oklch(0.985 0 0);
  --muted: oklch(0.269 0 0);
  --muted-foreground: oklch(0.708 0 0);
  --accent: oklch(0.269 0 0);
  --accent-foreground: oklch(0.985 0 0);
  --destructive: oklch(0.704 0.191 22.216);
  --destructive-foreground: oklch(0.985 0 0);
  --border: oklch(0.269 0 0);
  --input: oklch(0.269 0 0);
  --ring: oklch(0.556 0 0);

  --sidebar: oklch(0.205 0 0);
  --sidebar-foreground: oklch(0.985 0 0);
  --sidebar-primary: oklch(0.488 0.243 264.376);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.269 0 0);
  --sidebar-accent-foreground: oklch(0.985 0 0);
  --sidebar-border: oklch(0.269 0 0);
}

/* ============================================
   PINK THEME
   Pink/rose accents
   ============================================ */
.theme-pink {
  --background: oklch(0.991 0.006 325.601);
  --foreground: oklch(0.277 0.052 325.006);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.277 0.052 325.006);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.277 0.052 325.006);
  --primary: oklch(0.585 0.191 325.018);
  --primary-foreground: oklch(0.991 0.006 325.601);
  --secondary: oklch(0.965 0.015 325.612);
  --secondary-foreground: oklch(0.277 0.052 325.006);
  --muted: oklch(0.965 0.015 325.612);
  --muted-foreground: oklch(0.551 0.027 326.05);
  --accent: oklch(0.965 0.015 325.612);
  --accent-foreground: oklch(0.277 0.052 325.006);
  --destructive: oklch(0.577 0.245 27.325);
  --destructive-foreground: oklch(0.991 0.006 325.601);
  --border: oklch(0.924 0.021 325.466);
  --input: oklch(0.924 0.021 325.466);
  --ring: oklch(0.585 0.191 325.018);

  --sidebar: oklch(0.965 0.015 325.612);
  --sidebar-foreground: oklch(0.277 0.052 325.006);
  --sidebar-primary: oklch(0.585 0.191 325.018);
  --sidebar-primary-foreground: oklch(0.991 0.006 325.601);
  --sidebar-accent: oklch(0.924 0.021 325.466);
  --sidebar-accent-foreground: oklch(0.277 0.052 325.006);
  --sidebar-border: oklch(0.924 0.021 325.466);
}

.theme-pink.dark {
  --background: oklch(0.277 0.052 325.006);
  --foreground: oklch(0.991 0.006 325.601);
  --card: oklch(0.277 0.052 325.006);
  --card-foreground: oklch(0.991 0.006 325.601);
  --popover: oklch(0.277 0.052 325.006);
  --popover-foreground: oklch(0.991 0.006 325.601);
  --primary: oklch(0.585 0.191 325.018);
  --primary-foreground: oklch(0.277 0.052 325.006);
  --secondary: oklch(0.357 0.058 325.224);
  --secondary-foreground: oklch(0.991 0.006 325.601);
  --muted: oklch(0.357 0.058 325.224);
  --muted-foreground: oklch(0.715 0.031 325.612);
  --accent: oklch(0.357 0.058 325.224);
  --accent-foreground: oklch(0.991 0.006 325.601);
  --destructive: oklch(0.704 0.191 22.216);
  --destructive-foreground: oklch(0.991 0.006 325.601);
  --border: oklch(0.357 0.058 325.224);
  --input: oklch(0.357 0.058 325.224);
  --ring: oklch(0.585 0.191 325.018);

  --sidebar: oklch(0.317 0.055 325.115);
  --sidebar-foreground: oklch(0.991 0.006 325.601);
  --sidebar-primary: oklch(0.585 0.191 325.018);
  --sidebar-primary-foreground: oklch(0.277 0.052 325.006);
  --sidebar-accent: oklch(0.357 0.058 325.224);
  --sidebar-accent-foreground: oklch(0.991 0.006 325.601);
  --sidebar-border: oklch(0.357 0.058 325.224);
}

/* ============================================
   BASE STYLES
   ============================================ */
@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

## 5. Theme Toggle Component

A complete popover component for switching themes:

```tsx
import { useState, useRef, useEffect } from 'react';
import { useSpacemanTheme } from '@space-man/react-theme-animation';
import { Palette, Sun, Moon, Monitor, Check } from 'lucide-react';

const colorThemes = [
  { id: 'northern-lights', label: 'Northern Lights' },
  { id: 'default', label: 'Default' },
  { id: 'pink', label: 'Pink' }
];

const modes = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor }
];

export function ThemePopover() {
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const { theme, colorTheme, switchThemeFromElement, setColorTheme } = useSpacemanTheme();

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleModeChange = (mode: string, e: React.MouseEvent) => {
    switchThemeFromElement(mode, e.currentTarget);
    setIsOpen(false);
  };

  const handleColorChange = (themeId: string) => {
    setColorTheme(themeId);
  };

  return (
    <div className="relative" ref={popoverRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`p-2 rounded-md transition-colors ${
          isOpen
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        }`}
        aria-label="Toggle theme"
      >
        <Palette className="h-5 w-5" />
      </button>

      {/* Popover */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 rounded-md border border-border bg-popover p-2 shadow-lg z-50">
          {/* Color Themes */}
          <div className="mb-2">
            <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
              Color Theme
            </div>
            {colorThemes.map((ct) => (
              <button
                key={ct.id}
                onClick={() => handleColorChange(ct.id)}
                className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
              >
                {ct.label}
                {colorTheme === ct.id && <Check className="h-4 w-4" />}
              </button>
            ))}
          </div>

          <div className="my-2 h-px bg-border" />

          {/* Mode */}
          <div>
            <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
              Mode
            </div>
            {modes.map((m) => (
              <button
                key={m.id}
                onClick={(e) => handleModeChange(m.id, e)}
                className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
              >
                <span className="flex items-center gap-2">
                  <m.icon className="h-4 w-4" />
                  {m.label}
                </span>
                {theme === m.id && <Check className="h-4 w-4" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

## 6. Using Theme Colors in Components

```tsx
// Use semantic Tailwind classes
<div className="bg-background text-foreground">
  <header className="border-b border-border bg-card">
    <h1 className="text-foreground">Title</h1>
    <p className="text-muted-foreground">Subtitle</p>
  </header>

  <aside className="bg-sidebar text-sidebar-foreground">
    <button className="bg-sidebar-primary text-sidebar-primary-foreground">
      Primary Action
    </button>
    <button className="hover:bg-sidebar-accent hover:text-sidebar-accent-foreground">
      Secondary
    </button>
  </aside>

  <main className="bg-card text-card-foreground">
    <button className="bg-primary text-primary-foreground">
      Submit
    </button>
    <button className="bg-secondary text-secondary-foreground">
      Cancel
    </button>
    <button className="bg-destructive text-destructive-foreground">
      Delete
    </button>
  </main>
</div>
```

## How It Works

```
User clicks theme toggle
         ↓
useSpacemanTheme() hook called
         ↓
Provider updates React context + localStorage
         ↓
Classes applied to <html>: .theme-{name} and optionally .dark
         ↓
CSS cascade: :root → .theme-X → .theme-X.dark
         ↓
Tailwind utilities resolve to new CSS variable values
         ↓
500ms circular reveal animation plays from click origin
```

## System Preference Detection

When mode is set to "system":

1. Library detects `window.matchMedia('(prefers-color-scheme: dark)')`
2. Applies `.dark` class automatically if system prefers dark
3. Listens for changes and updates in real-time
4. Falls back to light mode if preference unavailable

## Browser Support

- CSS Custom Properties: All modern browsers (IE 11+ with polyfill)
- OKLch colors: Modern browsers (Chrome 111+, Firefox 113+, Safari 15.4+)
- `prefers-color-scheme`: All modern browsers

For broader OKLch support, you can convert to HSL or RGB values.

## Summary

| Feature | Implementation |
|---------|----------------|
| State management | `@space-man/react-theme-animation` provider + hook |
| Persistence | Automatic localStorage (built into library) |
| Dark mode strategy | Tailwind class-based (`darkMode: ["class"]`) |
| Color definitions | CSS variables in OKLch color space |
| Theme switching | `switchThemeFromElement(mode, element)` |
| Color scheme switching | `setColorTheme(themeId)` |
| Animation | 500ms circular reveal from click origin |
| System detection | Built-in, automatic when mode is "system" |
