# Generated by Django 3.0.6 on 2022-08-07 17:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0003_auto_20190319_1651'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderinfo',
            name='order_status',
            field=models.SmallIntegerField(choices=[(1, '待支付'), (2, '待发货'), (3, '待收货'), (4, '待评价'), (5, '已完成')], default=1, verbose_name='订单状态'),
        ),
        migrations.AlterField(
            model_name='orderinfo',
            name='trade_no',
            field=models.CharField(default='', max_length=128, verbose_name='支付编号'),
        ),
    ]
