let draggedElement = null;
let originalColumn = null;
let originalIndex = null;

function initializeKanbanBoard(boardId, csrfToken, moveEndpoint) {
    const board = document.getElementById(boardId);
    if (!board) return;

    const columns = board.querySelectorAll('[data-column-id]');

    columns.forEach(column => {
        if (column.dataset.canDrag !== 'true') return;

        new Sortable(column, {
            group: 'shared',
            animation: 150,
            ghostClass: 'opacity-50',
            dragClass: 'dragging',
            chosenClass: 'chosen',
            forceFallback: true,
            fallbackOnBody: true,
            swapThreshold: 0.65,

            onStart: function (evt) {
                draggedElement = evt.item;
                originalColumn = evt.from;
                originalIndex = evt.oldIndex;
                document.body.classList.add('dragging-active');
            },

            onEnd: async function (evt) {
                document.body.classList.remove('dragging-active');

                const taskId = evt.item.dataset.taskId;
                const newColumnId = evt.to.dataset.columnId;
                const newIndex = evt.newIndex;

                // Optimistically update counts
                updateColumnCounts(evt.from, evt.to);

                try {
                    const response = await fetch(
                        moveEndpoint.replace('{taskId}', taskId),
                        {
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': csrfToken,
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'Accept': 'application/json'
                            },
                            body: `column_id=${newColumnId}&position=${newIndex}`
                        }
                    );

                    const data = await response.json();

                    if (!data.ok) {
                        throw new Error(data.error || 'Move failed');
                    }

                    // Update with server counts
                    if (data.from_count !== undefined) {
                        updateBadgeCount(evt.from.dataset.columnId, data.from_count);
                    }
                    if (data.to_count !== undefined) {
                        updateBadgeCount(evt.to.dataset.columnId, data.to_count);
                    }

                } catch (error) {
                    // Revert the move
                    revertMove(evt);
                    showNotification(error.message || 'Could not move task', 'error');
                }
            }
        });
    });
}

function revertMove(evt) {
    if (originalColumn && draggedElement) {
        const children = Array.from(originalColumn.children);
        const referenceNode = children[originalIndex] || null;

        if (referenceNode) {
            originalColumn.insertBefore(draggedElement, referenceNode);
        } else {
            originalColumn.appendChild(draggedElement);
        }

        updateColumnCounts(evt.to, originalColumn);
    }
}

function updateColumnCounts(fromColumn, toColumn) {
    if (fromColumn) {
        const fromCount = fromColumn.querySelectorAll('[data-task-id]').length;
        updateBadgeCount(fromColumn.dataset.columnId, fromCount);
    }
    if (toColumn && toColumn !== fromColumn) {
        const toCount = toColumn.querySelectorAll('[data-task-id]').length;
        updateBadgeCount(toColumn.dataset.columnId, toCount);
    }
}

function updateBadgeCount(columnId, count) {
    const badge = document.querySelector(`[data-column-count="${columnId}"]`);
    if (badge) {
        badge.textContent = count;
    }
}

function showNotification(message, type = 'info') {
    // Use your notification system here
    const toast = document.createElement('div');
    toast.className = `toast toast-end`;
    toast.innerHTML = `
        <div class="alert alert-${type === 'error' ? 'error' : 'info'}">
            <span>${message}</span>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}