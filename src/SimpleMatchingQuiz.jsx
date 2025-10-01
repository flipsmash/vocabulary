import React, { useState, useEffect } from 'react';

const SimpleMatchingQuiz = ({ questionId, terms, definitions, correctMatches, onAssignmentChange }) => {
  const [assignments, setAssignments] = useState({});
  const [draggedDefinition, setDraggedDefinition] = useState(null);

  // Notify parent when assignments change
  useEffect(() => {
    console.log('Assignments changed:', assignments);
    if (onAssignmentChange) {
      console.log('Calling onAssignmentChange with:', assignments);
      onAssignmentChange(assignments);
    } else {
      console.log('No onAssignmentChange callback provided');
    }
  }, [assignments, onAssignmentChange]);

  // Check if all terms are assigned
  const isComplete = () => {
    return terms.every((_, index) => assignments[index] !== undefined);
  };

  // Handle drag start
  const handleDragStart = (e, definitionIndex) => {
    setDraggedDefinition(definitionIndex);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', definitionIndex.toString());
  };

  // Handle drag over (required for drop to work)
  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  // Handle drop on term
  const handleDrop = (e, termIndex) => {
    e.preventDefault();
    const definitionIndex = parseInt(e.dataTransfer.getData('text/plain'));

    // Don't allow drop if term already has a definition
    if (assignments[termIndex] !== undefined) {
      return;
    }

    // Make the assignment
    setAssignments(prev => ({
      ...prev,
      [termIndex]: definitionIndex
    }));

    setDraggedDefinition(null);
  };

  // Remove assignment
  const removeAssignment = (termIndex) => {
    setAssignments(prev => {
      const newAssignments = { ...prev };
      delete newAssignments[termIndex];
      return newAssignments;
    });
  };

  // Check if definition is already assigned
  const isDefinitionAssigned = (definitionIndex) => {
    return Object.values(assignments).includes(definitionIndex);
  };

  return (
    <div>
      {/* Instructions */}
      <div className="matching-instructions mb-4 p-3 bg-light border-start border-4 border-primary">
        <h6 className="text-primary mb-2">🎯 How to Match</h6>
        <p className="mb-0 small">
          <strong>Drag & Drop:</strong> Drag definitions from the bank onto terms.
          <strong>Remove:</strong> Click the ✕ button on placed definitions.
        </p>
      </div>

      <div className="row">
        {/* Terms Column */}
        <div className="col-lg-7">
          <h6 className="text-primary mb-3">📝 Terms</h6>
          <div className="terms-list">
            {terms.map((term, termIndex) => (
              <div key={termIndex} className="term-slot card mb-3 p-3">
                <div className="d-flex align-items-start">
                  <div className="term-number badge bg-primary me-3 flex-shrink-0">
                    {termIndex + 1}
                  </div>
                  <div className="flex-grow-1">
                    <strong className="term-text d-block mb-2">{term}</strong>

                    {/* Drop Zone */}
                    <div
                      className={`drop-zone ${assignments[termIndex] !== undefined ? 'has-definition' : 'empty'}`}
                      onDragOver={handleDragOver}
                      onDrop={(e) => handleDrop(e, termIndex)}
                      style={{
                        minHeight: '80px',
                        border: '3px dashed #dee2e6',
                        borderRadius: '8px',
                        padding: '12px',
                        backgroundColor: assignments[termIndex] !== undefined ? '#d4edda' : '#f8f9fa',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      {assignments[termIndex] !== undefined ? (
                        <div className="assigned-definition w-100">
                          <div className="d-flex justify-content-between align-items-start">
                            <span className="definition-text flex-grow-1">
                              {definitions[assignments[termIndex]]}
                            </span>
                            <button
                              className="btn btn-sm btn-outline-danger ms-2"
                              onClick={() => removeAssignment(termIndex)}
                              title="Remove this assignment"
                            >
                              ✕
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="drop-placeholder text-center text-muted">
                          Drop definition here
                        </div>
                      )}
                    </div>

                    {/* Hidden input for form submission */}
                    <input
                      type="hidden"
                      name={`match_${questionId}_${termIndex}`}
                      value={assignments[termIndex] || ''}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Definitions Bank */}
        <div className="col-lg-5">
          <h6 className="text-success mb-3">📚 Available Definitions</h6>
          <div className="definitions-bank p-3 border rounded" style={{ minHeight: '400px' }}>
            {definitions.map((definition, index) => (
              <div
                key={index}
                className={`definition-item card mb-2 p-3 ${isDefinitionAssigned(index) ? 'text-muted opacity-50' : 'border-success'}`}
                draggable={!isDefinitionAssigned(index)}
                onDragStart={(e) => handleDragStart(e, index)}
                style={{
                  cursor: isDefinitionAssigned(index) ? 'not-allowed' : 'grab',
                  userSelect: 'none'
                }}
              >
                <div className="d-flex align-items-center">
                  <div className="drag-handle me-2 text-muted">⋮⋮</div>
                  <div className="definition-text flex-grow-1">{definition}</div>
                </div>
              </div>
            ))}

            {definitions.every((_, index) => isDefinitionAssigned(index)) && (
              <div className="text-center text-muted p-4">
                <em>All definitions have been assigned</em>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Completion indicator */}
      {isComplete() && (
        <div className="alert alert-success mt-3">
          <strong>✅ All terms matched!</strong> You can proceed to the next question.
        </div>
      )}
    </div>
  );
};

export default SimpleMatchingQuiz;