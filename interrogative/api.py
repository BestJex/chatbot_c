# -*- coding: utf-8 -*-
"""
API
----
ALL application can be use
"""
from interrogative.model import get_model

__all__ = ["train", "recognize"]


def train():
    """
    model training
    """
    model = get_model()
    model.train()


def recognize(sentence):
    """
    interrogative sentence recognize
    """
    model = get_model()
    prob = model.predict(sentence)[0]
    print(prob)
    return True if prob > 0.5 else False

if __name__ == '__main__':
    train()
