#/////////////////////////////////#
#   UNIFIED CHRONOLOGICAL STACK   #
#/////////////////////////////////#

class HistoryManager:
    """
    Unified chronological action stack for editing software.
    Every operation (drawing strokes, bucket fills, OCR scans, and AI clean inpainting)
    is recorded in a single ordered timeline.
    Ctrl+Z steps backward through this timeline, and Ctrl+Shift+Z / Ctrl+Y steps forward.
    """
    def __init__(self, limit=30):
        self.limit = limit
        self.undo_stack = []
        self.redo_stack = []

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def push_mask_state(self, mask_qimage):
        """Pushes a mask snapshot to the unified undo stack before a modification."""
        if mask_qimage is None:
            return
        self.undo_stack.append({
            "type": "mask",
            "mask": mask_qimage.copy()
        })
        self.redo_stack.clear()
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)

    def push_image_clean(self, patches, result_img, saved_mask=None):
        """
        Pushes an AI clean action to the unified stack.
        Stores the pre-clean original patches (for undo), post-clean patches (for redo),
        and the mask that was cleaned (so undo restores the user's mask).
        """
        patch_records = []
        for x, y, undo_patch in patches:
            h, w = undo_patch.shape[:2]
            redo_patch = result_img[y:y+h, x:x+w].copy()
            patch_records.append((x, y, undo_patch.copy(), redo_patch))

        self.undo_stack.append({
            "type": "image",
            "patches": patch_records,
            "saved_mask": saved_mask.copy() if saved_mask else None
        })
        self.redo_stack.clear()
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)

    def push_image_action(self, x, y, patch):
        """Legacy compatibility wrapper for single patch push."""
        self.undo_stack.append({
            "type": "image_legacy",
            "x": x,
            "y": y,
            "patch": patch.copy()
        })
        self.redo_stack.clear()
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)

    def undo(self, current_img, current_mask):
        """
        Pops the latest action and returns the restored state.
        Returns a dict describing the changes, or None if undo stack is empty.
        """
        if not self.undo_stack:
            return None

        action = self.undo_stack.pop()
        act_type = action["type"]

        if act_type == "mask":
            if current_mask is not None:
                self.redo_stack.append({
                    "type": "mask",
                    "mask": current_mask.copy()
                })
            return {
                "type": "mask",
                "mask": action["mask"]
            }

        elif act_type == "image":
            self.redo_stack.append(action)
            if current_img is not None:
                for x, y, undo_patch, _ in action["patches"]:
                    h, w = undo_patch.shape[:2]
                    current_img[y:y+h, x:x+w] = undo_patch

            return {
                "type": "image",
                "img": current_img,
                "restore_mask": action.get("saved_mask")
            }

        elif act_type == "image_legacy":
            x, y, patch = action["x"], action["y"], action["patch"]
            h, w = patch.shape[:2]
            if current_img is not None:
                redo_patch = current_img[y:y+h, x:x+w].copy()
                self.redo_stack.append({
                    "type": "image_legacy",
                    "x": x,
                    "y": y,
                    "patch": redo_patch
                })
                current_img[y:y+h, x:x+w] = patch
            return {
                "type": "image",
                "img": current_img,
                "restore_mask": None
            }

        return None

    def redo(self, current_img, current_mask):
        """
        Re-applies the latest undone action in chronological order.
        Returns a dict describing the changes, or None if redo stack is empty.
        """
        if not self.redo_stack:
            return None

        action = self.redo_stack.pop()
        act_type = action["type"]

        if act_type == "mask":
            if current_mask is not None:
                self.undo_stack.append({
                    "type": "mask",
                    "mask": current_mask.copy()
                })
            return {
                "type": "mask",
                "mask": action["mask"]
            }

        elif act_type == "image":
            self.undo_stack.append(action)
            if current_img is not None:
                for x, y, _, redo_patch in action["patches"]:
                    h, w = redo_patch.shape[:2]
                    current_img[y:y+h, x:x+w] = redo_patch

            return {
                "type": "image",
                "img": current_img,
                "clear_mask": True
            }

        elif act_type == "image_legacy":
            x, y, patch = action["x"], action["y"], action["patch"]
            h, w = patch.shape[:2]
            if current_img is not None:
                undo_patch = current_img[y:y+h, x:x+w].copy()
                self.undo_stack.append({
                    "type": "image_legacy",
                    "x": x,
                    "y": y,
                    "patch": undo_patch
                })
                current_img[y:y+h, x:x+w] = patch
            return {
                "type": "image",
                "img": current_img,
                "clear_mask": True
            }

        return None

    # Legacy method compatibility wrappers
    def pop_image_undo(self, current_img):
        res = self.undo(current_img, None)
        return res

    def pop_image_redo(self, current_img):
        res = self.redo(current_img, None)
        return res

    def pop_mask_undo(self, current_mask):
        res = self.undo(None, current_mask)
        return res.get("mask") if res else None

    def pop_mask_redo(self, current_mask):
        res = self.redo(None, current_mask)
        return res.get("mask") if res else None