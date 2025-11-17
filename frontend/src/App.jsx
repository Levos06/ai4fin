import React, { useState, useRef, useEffect } from 'react'
import ChatInterface from './components/ChatInterface'
import './App.css'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Financial AI Agent</h1>
        <p>Интеллектуальный помощник для финансового анализа</p>
      </header>
      <main className="app-main">
        <ChatInterface />
      </main>
    </div>
  )
}

export default App

