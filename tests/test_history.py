import unittest
from lyst.history import SESSION_FILE, history_summary, save_history, load_history, clear_history

class TestHistory(unittest.TestCase):
    def test_history_accumulation(self):
        history = []
        
        question1 = "What is the total sales for last month?"
        answer1 = "The total sales for last month were $10,000."
        history.append({"role": "user", "content": question1})
        history.append({"role": "assistant", "content": answer1})
        
        question2 = "What about the sales for this month?"
        answer2 = "The sales for this month so far are $5,000."
        history.append({"role": "user", "content": question2})
        history.append({"role": "assistant", "content": answer2})
        
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], question1)
        self.assertEqual(history[1]["content"], answer1)
        self.assertEqual(history[2]["content"], question2)
        self.assertEqual(history[3]["content"], answer2)

    def test_history_truncation(self):
        history = []
        for i in range(12):
            history.append({"role": "user", "content": f"Question {i+1}"})
            history.append({"role": "assistant", "content": f"Answer {i+1}"})
        
        max_messages = 20
        if len(history) > max_messages:
            history = history[-max_messages:]
        
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0]["content"], "Question 3")
        self.assertEqual(history[1]["content"], "Answer 3")
        self.assertEqual(history[-2]["content"], "Question 12")
        self.assertEqual(history[-1]["content"], "Answer 12")

    def test_clear_history(self):
        history = [{"role": "user", "content": "Some question"}, {"role": "assistant", "content": "Some answer"}]
        history.clear()
        self.assertEqual(len(history), 0)
    
    def test_history_summary(self):
        
        clear_history()
        self.assertEqual(history_summary(), "No active session.")
        
        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
        ]
        save_history(messages)
        self.assertEqual(history_summary(), f"2 exchange(s) in current session. ({SESSION_FILE})")

    def test_load_history(self):
        clear_history()
        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
        ]
        save_history(messages)
        loaded_messages = load_history()
        self.assertEqual(loaded_messages, messages)


if __name__ == "__main__":
    unittest.main()