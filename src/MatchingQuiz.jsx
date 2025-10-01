import React, { useState, useEffect } from 'react';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

const MatchingQuiz = ({ questionId, terms, definitions, correctMatches, onAssignmentChange }) => {
  const [assignments, setAssignments] = useState({});
  const [availableDefinitions, setAvailableDefinitions] = useState(definitions);

  // Notify parent component when assignments change
  useEffect(() => {
    if (onAssignmentChange) {
      onAssignmentChange(assignments);
    }
  }, [assignments, onAssignmentChange]);

  const handleDragEnd = (result) => {
    // Re-enable text selection
    document.body.style.userSelect = '';

    const { source, destination } = result;

    // If dropped outside valid area
    if (!destination) return;

    const sourceId = source.droppableId;
    const destId = destination.droppableId;
    const definitionIndex = parseInt(result.draggableId);

    // If dropped on same place
    if (sourceId === destId && source.index === destination.index) return;

    if (destId.startsWith('term-')) {
      // Dropped on a term
      const termIndex = parseInt(destId.replace('term-', ''));

      // Check if term already has definition
      if (assignments[termIndex] !== undefined) return;

      // Make assignment
      setAssignments(prev => ({
        ...prev,
        [termIndex]: definitionIndex
      }));

      // Remove from available if coming from definitions bank
      if (sourceId === 'definitions-bank') {
        setAvailableDefinitions(prev =>
          prev.filter(def => definitions.indexOf(def) !== definitionIndex)
        );
      }
    } else if (destId === 'definitions-bank') {
      // Dropped back to definitions bank
      if (sourceId.startsWith('term-')) {
        const termIndex = parseInt(sourceId.replace('term-', ''));

        // Remove assignment
        setAssignments(prev => {
          const newAssignments = { ...prev };
          delete newAssignments[termIndex];
          return newAssignments;
        });

        // Add back to available definitions
        setAvailableDefinitions(prev => [...prev, definitions[definitionIndex]]);
      }
    } else if (sourceId.startsWith('term-') && destId.startsWith('term-')) {
      // Moving between terms
      const sourceTerm = parseInt(sourceId.replace('term-', ''));
      const destTerm = parseInt(destId.replace('term-', ''));

      // Check if destination term already has definition
      if (assignments[destTerm] !== undefined) return;

      // Move assignment
      setAssignments(prev => {
        const newAssignments = { ...prev };
        newAssignments[destTerm] = definitionIndex;
        delete newAssignments[sourceTerm];
        return newAssignments;
      });
    }
  };

  const isComplete = () => {
    return terms.every((_, index) => assignments[index] !== undefined);
  };

  return (
    <DragDropContext
      onDragEnd={handleDragEnd}
      onDragStart={() => {
        // Disable text selection during drag
        document.body.style.userSelect = 'none';
      }}
      onDragUpdate={() => {
        // Keep selection disabled
        document.body.style.userSelect = 'none';
      }}
    >
      <div className="row">
        {/* Terms Column */}
        <div className="col-lg-7">
          <h6 className="text-primary mb-3">📝 Terms</h6>
          <div className="terms-list">
            {terms.map((term, termIndex) => (
              <div key={termIndex} className="term-slot card mb-3 p-3 position-relative">
                <div className="d-flex align-items-start">
                  <div className="term-number badge bg-primary me-3 flex-shrink-0">
                    {termIndex + 1}
                  </div>
                  <div className="flex-grow-1">
                    <strong className="term-text d-block mb-2">{term}</strong>

                    <Droppable droppableId={`term-${termIndex}`}>
                      {(provided, snapshot) => (
                        <div
                          ref={provided.innerRef}
                          {...provided.droppableProps}
                          className={`definition-drop-area ${
                            snapshot.isDraggingOver ? 'drag-over' : ''
                          }`}
                          style={{
                            minHeight: '100px',
                            backgroundColor: snapshot.isDraggingOver ? '#e3f2fd' : '#f8f9fa',
                            border: snapshot.isDraggingOver ? '4px solid #2196f3' : '3px dashed #dee2e6',
                            borderRadius: '12px',
                            padding: '16px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: '100%'
                          }}
                        >
                          {assignments[termIndex] !== undefined ? (
                            // Show assigned definition
                            <Draggable
                              draggableId={assignments[termIndex].toString()}
                              index={0}
                            >
                              {(provided, snapshot) => (
                                <div
                                  ref={provided.innerRef}
                                  {...provided.draggableProps}
                                  {...provided.dragHandleProps}
                                  className={`assigned-definition card border-success bg-light p-2 mb-0 ${
                                    snapshot.isDragging ? 'dragging' : ''
                                  }`}
                                >
                                  <div className="d-flex justify-content-between align-items-start">
                                    <span className="definition-text flex-grow-1">
                                      {definitions[assignments[termIndex]]}
                                    </span>
                                    <button
                                      className="btn btn-sm btn-outline-danger ms-2"
                                      onClick={() => {
                                        const defIndex = assignments[termIndex];
                                        setAssignments(prev => {
                                          const newAssignments = { ...prev };
                                          delete newAssignments[termIndex];
                                          return newAssignments;
                                        });
                                        setAvailableDefinitions(prev => [...prev, definitions[defIndex]]);
                                      }}
                                      title="Remove this assignment"
                                    >
                                      ✕
                                    </button>
                                  </div>
                                </div>
                              )}
                            </Draggable>
                          ) : (
                            // Show placeholder
                            <div className="drop-placeholder text-center p-3 border border-2 border-dashed rounded border-muted">
                              <span className="text-muted">Drop definition here</span>
                            </div>
                          )}
                          {provided.placeholder}
                        </div>
                      )}
                    </Droppable>
                  </div>
                </div>

                {/* Hidden inputs for form submission */}
                <input
                  type="hidden"
                  name={`match_${questionId}_${termIndex}`}
                  value={assignments[termIndex] || ''}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Definitions Column */}
        <div className="col-lg-5">
          <h6 className="text-success mb-3">📚 Available Definitions</h6>

          <Droppable droppableId="definitions-bank">
            {(provided, snapshot) => (
              <div
                ref={provided.innerRef}
                {...provided.droppableProps}
                className={`definitions-bank p-3 border rounded ${
                  snapshot.isDraggingOver ? 'drag-over' : ''
                }`}
                style={{ minHeight: '400px' }}
              >
                {availableDefinitions.map((definition, index) => {
                  // Find original index in definitions array
                  const originalIndex = definitions.indexOf(definition);
                  return (
                    <Draggable
                      key={originalIndex}
                      draggableId={originalIndex.toString()}
                      index={index}
                    >
                      {(provided, snapshot) => (
                        <div
                          ref={provided.innerRef}
                          {...provided.draggableProps}
                          className={`definition-item card mb-2 p-3 border-success ${
                            snapshot.isDragging ? 'dragging' : ''
                          }`}
                          style={{
                            ...provided.draggableProps.style,
                            display: 'flex',
                            alignItems: 'center',
                            userSelect: 'none'
                          }}
                        >
                          <div
                            {...provided.dragHandleProps}
                            style={{
                              cursor: 'grab',
                              marginRight: '8px',
                              color: '#6c757d',
                              padding: '4px'
                            }}
                          >
                            ⋮⋮
                          </div>
                          <div style={{ flexGrow: 1 }}>{definition}</div>
                        </div>
                      )}
                    </Draggable>
                  );
                })}
                {provided.placeholder}

                {availableDefinitions.length === 0 && (
                  <div className="text-center text-muted p-4">
                    <em>All definitions have been assigned</em>
                  </div>
                )}
              </div>
            )}
          </Droppable>
        </div>
      </div>

      {/* Completion indicator */}
      {isComplete() && (
        <div className="alert alert-success mt-3">
          <strong>✅ All terms matched!</strong> You can proceed to the next question.
        </div>
      )}
    </DragDropContext>
  );
};

export default MatchingQuiz;