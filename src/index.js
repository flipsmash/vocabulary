import React from 'react';
import { createRoot } from 'react-dom/client';
import SimpleMatchingQuiz from './SimpleMatchingQuiz.jsx';

// Global function to mount React component
window.mountMatchingQuiz = (elementId, props) => {
  const container = document.getElementById(elementId);
  if (container) {
    const root = createRoot(container);
    root.render(React.createElement(SimpleMatchingQuiz, props));
    return root;
  }
  console.error('Container element not found:', elementId);
};

// Global function to handle quiz completion for Next button
window.checkMatchingComplete = (questionId) => {
  // This will be called by the existing quiz navigation logic
  const container = document.getElementById(`matching-quiz-${questionId}`);
  if (container && container._reactRoot) {
    // Check if all terms are assigned
    const hiddenInputs = container.querySelectorAll('input[type="hidden"]');
    return Array.from(hiddenInputs).every(input => input.value !== '');
  }
  return false;
};

export { SimpleMatchingQuiz };